# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Widget « Analyse » (ARC-25) : un outil d'analyse spatiale = UNE op de pipeline existante
(`OperationContract`) appliquée à un dataset, sans nouveau moteur ni nouvelle op.

Le service synthétise un mini-pipeline `reader.collection -> transform.<op> [-> select -> writer]` et le
confie au runtime de pipeline, dont le reader lit le lac GeoParquet PAR LE MÊME CHEMIN que
`POST /collections/{id}/aggregate` (`_dedup_cte`) : colonnes sensibles retirées (GAP-22), refus fail-closed
d'une collection à limites géographiques (GAP-27), `can(read)` ; mêmes bornes DuckDB (mémoire, threads,
temp, `open_connection`) ; sortie éphémère = `preview_pipeline` (durée bornée), sortie collection =
`create_empty_collection` (quotas, `data.manage`) puis `writer.collection` (`can(write)`, validation,
audit). Aucun nouveau chemin de lecture."""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import is_raster_enabled
from app.collections.introspection import (
    ColumnInfo,
    Introspector,
    TableInfo,
    hide_sensitive_columns,
)
from app.collections.provisioning import create_empty_collection
from app.collections.schemas import EmptyCollectionColumn
from app.configs.schemas import PipelineEdge, PipelineNode, PipelinePayload
from app.pipelines import compiler
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline, run_pipeline
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

EPHEMERAL_MAX_FEATURES = 5000
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,58}$")
_RESERVED_COLUMNS = {"id", "tenant_id", "geom", "geometry"}
_SQL_TYPE = {
    "string": "text",
    "enum": "text",
    "integer": "bigint",
    "number": "double precision",
    "boolean": "boolean",
    "date": "date",
    "datetime": "timestamptz",
}
_MULTI = {
    "Point": "MultiPoint",
    "MultiPoint": "MultiPoint",
    "LineString": "MultiLineString",
    "MultiLineString": "MultiLineString",
    "Polygon": "MultiPolygon",
    "MultiPolygon": "MultiPolygon",
}


class AnalysisError(Exception):
    """Entrée invalide (422) — jamais un 500."""


def max_features() -> int:
    """Plafond d'entités d'une collection analysable (borne de coût, hors timeout DuckDB)."""
    return int(os.environ.get("CORE_ANALYSIS_MAX_FEATURES") or 100_000)


# --- paramètres propres à chaque outil (schéma + aide pour le widget et le MCP) -----------------------


class BufferArgs(BaseModel):
    distance: float = Field(..., gt=0, le=1_000_000, description="Rayon du tampon.")
    unit: Literal["meters", "native"] = Field(
        "meters",
        description="meters = en mètres réels (projection azimutale locale par entité) ; native = unité du CRS.",
    )


class NoArgs(BaseModel):
    pass


class IntersectionArgs(BaseModel):
    outputGeometry: Literal["left", "intersection"] = Field(
        "intersection", description="Géométrie rendue : la zone commune, ou la géométrie d'origine."
    )


class CountWithinArgs(BaseModel):
    countColumn: str = Field("count", description="Nom de la colonne de comptage ajoutée.")
    predicate: Literal["intersects", "contains"] = Field(
        "intersects",
        description="intersects = touche ou recouvre ; contains = l'autre jeu est contenu.",
    )


class DissolveArgs(BaseModel):
    groupBy: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Champs de regroupement ; vide = tout fusionner.",
    )


class SimplifyArgs(BaseModel):
    tolerance: float = Field(
        ..., gt=0, description="Tolérance de simplification, en unités du CRS."
    )
    preserveTopology: bool = Field(True, description="Évite les auto-intersections.")


class BoundingArgs(BaseModel):
    mode: Literal["envelope", "orientedRectangle"] = Field(
        "envelope", description="Boîte alignée aux axes ou rectangle orienté minimal."
    )


class ReprojectArgs(BaseModel):
    targetCrs: str = Field(..., pattern=r"^EPSG:\d+$", description="CRS cible, ex. EPSG:2154.")


class ZonalStatsArgs(BaseModel):
    rasterItemId: str = Field(
        ..., min_length=1, title="Raster", description="Raster (COG hébergé) à résumer."
    )
    band: int = Field(1, ge=1, title="Bande", description="Bande du raster.")
    stats: list[Literal["count", "min", "max", "mean", "sum", "std"]] = Field(
        default_factory=lambda: ["count", "mean", "min", "max"],
        title="Statistiques",
        min_length=1,
        max_length=6,
        description="Statistiques, séparées par des virgules : count, min, max, mean, sum, std.",
    )


@dataclass(frozen=True)
class AnalysisTool:
    name: str
    label: str
    help: str
    op: str  # op de pipeline réutilisée (OperationContract), jamais une nouvelle
    args: type[BaseModel]
    needs_other: bool = False
    # (géométrie source -> type de géométrie de la collection de sortie) ; None = non déterminable
    out_geometry: Callable[[str | None], str | None] = lambda g: _MULTI.get(g or "")
    op_params: Callable[[BaseModel], dict[str, Any]] = lambda a: a.model_dump()
    # colonnes propriétés conservées en sortie (None = toutes) et colonnes ajoutées
    keep: Callable[[BaseModel, list[str]], list[str]] = lambda a, cols: cols
    added: Callable[[BaseModel], list[tuple[str, str]]] = lambda a: []
    # capacité d'instance optionnelle (outil absent du catalogue et refusé si éteinte)
    enabled: Callable[[], bool] = lambda: True


_POLYGON = lambda g: "MultiPolygon"  # noqa: E731
_POINT = lambda g: "Point"  # noqa: E731

TOOLS: dict[str, AnalysisTool] = {
    t.name: t
    for t in [
        AnalysisTool(
            "buffer",
            "Tampon",
            "Zone tampon autour de chaque entité (distance en mètres par défaut).",
            "transform.buffer",
            BufferArgs,
            out_geometry=_POLYGON,
        ),
        AnalysisTool(
            "intersection",
            "Intersection",
            "Découpe les entités par un second jeu de données : ne garde que ce qui l'intersecte.",
            "transform.intersection",
            IntersectionArgs,
            needs_other=True,
            op_params=lambda a: {**a.model_dump(), "how": "inner"},
        ),
        AnalysisTool(
            "spatialJoin",
            "Sélection par localisation",
            "Garde les entités qui intersectent un second jeu (jointure spatiale sur le prédicat « intersecte » ; "
            "les attributs du second jeu ne sont pas rapportés).",
            "transform.intersection",
            NoArgs,
            needs_other=True,
            op_params=lambda a: {"how": "inner", "outputGeometry": "left"},
        ),
        AnalysisTool(
            "countWithin",
            "Comptage par entité",
            "Compte, pour chaque entité, les entités d'un second jeu qui l'intersectent ou qu'elle contient.",
            "transform.countWithin",
            CountWithinArgs,
            needs_other=True,
            added=lambda a: [(a.countColumn, "bigint")],  # type: ignore[attr-defined]
        ),
        AnalysisTool(
            "dissolve",
            "Fusion (dissolve)",
            "Fusionne les géométries, éventuellement par valeur d'un ou plusieurs champs.",
            "transform.aggregate",
            DissolveArgs,
            op_params=lambda a: {
                "groupBy": a.groupBy,  # type: ignore[attr-defined]
                "metrics": {"geometry": "ST_Union_Agg(geometry)"},
            },
            keep=lambda a, cols: list(a.groupBy),  # type: ignore[attr-defined]
        ),
        AnalysisTool(
            "centroid",
            "Centroïde",
            "Remplace chaque géométrie par son centre de gravité.",
            "transform.centroid",
            NoArgs,
            out_geometry=_POINT,
        ),
        AnalysisTool(
            "convexHull",
            "Enveloppe convexe",
            "Remplace chaque géométrie par son enveloppe convexe.",
            "transform.convexHull",
            NoArgs,
            out_geometry=_POLYGON,
        ),
        AnalysisTool(
            "simplify",
            "Simplification",
            "Réduit le nombre de sommets selon une tolérance.",
            "transform.simplify",
            SimplifyArgs,
        ),
        AnalysisTool(
            "boundingGeometry",
            "Boîte englobante",
            "Remplace chaque géométrie par sa boîte englobante.",
            "transform.boundingGeometry",
            BoundingArgs,
            out_geometry=_POLYGON,
        ),
        AnalysisTool(
            "reproject",
            "Reprojection",
            "Change le système de coordonnées des géométries.",
            "transform.reproject",
            ReprojectArgs,
        ),
        AnalysisTool(
            "zonalStats",
            "Statistiques raster par zone",
            "Résume une bande d'un raster sous chaque polygone (au plus 1 000 polygones) : "
            "une colonne zonal_<statistique> par statistique demandée.",
            "transform.zonalStats",
            ZonalStatsArgs,
            op_params=lambda a: {
                "itemId": a.rasterItemId,  # type: ignore[attr-defined]
                "band": a.band,  # type: ignore[attr-defined]
                "stats": a.stats,  # type: ignore[attr-defined]
            },
            added=lambda a: [
                (f"zonal_{s}", "double precision")
                for s in dict.fromkeys(a.stats)  # type: ignore[attr-defined]
            ],
            enabled=is_raster_enabled,
        ),
    ]
}


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "label": t.label,
            "help": t.help,
            "needsOtherCollection": t.needs_other,
            "paramsSchema": t.args.model_json_schema(),
        }
        for t in TOOLS.values()
        if t.enabled()
    ]


# --- exécution ----------------------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    otherCollectionId: str | None = None
    output: Literal["ephemeral", "collection"] = "ephemeral"
    title: str | None = Field(
        None, min_length=1, description="Titre de la collection créée (output=collection)."
    )
    limit: int = Field(1000, ge=1, le=EPHEMERAL_MAX_FEATURES)


def _prop_columns(info: TableInfo) -> list[ColumnInfo]:
    skip = {info.pk_column, "tenant_id", info.geometry_column}
    return [c for c in info.columns if c.name not in skip]


def _validate(
    req: AnalysisRequest, info: TableInfo, other: TableInfo | None, feature_count: int | None
) -> tuple[AnalysisTool, BaseModel]:
    tool = TOOLS.get(req.tool)
    if tool is None or not tool.enabled():
        raise AnalysisError(
            f"outil inconnu '{req.tool}' (disponibles : {', '.join(n for n, t in TOOLS.items() if t.enabled())})"
        )
    try:
        args = tool.args.model_validate(req.params)
    except ValidationError as exc:
        raise AnalysisError(
            f"paramètres invalides pour '{tool.name}' : {exc.errors()[0]['msg']}"
        ) from exc
    if tool.needs_other and not req.otherCollectionId:
        raise AnalysisError(f"'{tool.name}' exige otherCollectionId (second jeu de données)")
    if not tool.needs_other and req.otherCollectionId:
        raise AnalysisError(f"'{tool.name}' n'accepte pas otherCollectionId")
    if info.geometry_column is None:
        raise AnalysisError("la collection n'a pas de géométrie")
    if other is not None and other.geometry_column is None:
        raise AnalysisError("la seconde collection n'a pas de géométrie")
    visible = {c.name for c in _prop_columns(info)}
    for field in getattr(args, "groupBy", []):
        if field not in visible:
            raise AnalysisError(f"champ de regroupement inconnu ou non lisible : '{field}'")
    cc = getattr(args, "countColumn", None)
    if cc is not None and (not _IDENT.match(cc) or cc in _RESERVED_COLUMNS or cc in visible):
        raise AnalysisError(f"nom de colonne de comptage invalide ou déjà utilisé : '{cc}'")
    if feature_count is not None and feature_count > max_features():
        raise AnalysisError(
            f"collection trop volumineuse pour l'analyse ({feature_count} > {max_features()} entités)"
        )
    if req.output == "collection" and not req.title:
        raise AnalysisError("title est obligatoire avec output=collection")
    return tool, args


def _srids(tool: AnalysisTool, op_params: dict, info: TableInfo, other: TableInfo | None) -> int:
    try:
        return compiler.transform_output_srid(
            tool.op,
            op_params,
            input_srid=info.srid or 4326,
            join_srid=(other.srid or 4326) if other else None,
        )
    except ValueError as exc:
        raise AnalysisError(str(exc)) from exc


def _payload(
    tool: AnalysisTool,
    op_params: dict,
    req: AnalysisRequest,
    *,
    source_id: str,
    out_srid: int,
    keep_columns: list[str] | None,
    target_collection_id: str | None,
) -> tuple[PipelinePayload, str]:
    params = dict(op_params)
    if tool.needs_other:
        params["withCollectionId"] = req.otherCollectionId
    nodes = [
        PipelineNode(
            id="r1", kind="reader", op="reader.collection", params={"collectionId": source_id}
        ),
        PipelineNode(id="t1", kind="transform", op=tool.op, params=params),
    ]
    last = "t1"

    def chain(node: PipelineNode) -> None:
        nonlocal last
        nodes.append(node)
        last = node.id

    if target_collection_id is not None:
        if keep_columns is not None:
            chain(
                PipelineNode(
                    id="t2",
                    kind="transform",
                    op="transform.select",
                    params={"columns": {c: None for c in [*keep_columns, "geometry"]}},
                )
            )
        chain(
            PipelineNode(
                id="w1",
                kind="writer",
                op="writer.collection",
                params={"collectionId": target_collection_id, "mode": "append"},
            )
        )
    elif out_srid != 4326:  # le widget carte attend du WGS84
        chain(
            PipelineNode(
                id="t2",
                kind="transform",
                op="transform.reproject",
                params={"targetCrs": "EPSG:4326"},
            )
        )
    result_node = last
    if target_collection_id is None:
        # PipelinePayload exige un writer : l'aperçu s'arrête avant lui (up_to), il n'est jamais exécuté.
        nodes.append(
            PipelineNode(
                id="w0",
                kind="writer",
                op="writer.export",
                params={"format": "geojson", "key": "analysis"},
            )
        )
    edges = []
    prev = "r1"
    for n in nodes[1:]:
        edges.append(PipelineEdge(id=f"e_{prev}_{n.id}", **{"from": prev}, to=n.id))
        prev = n.id
    return PipelinePayload(nodes=nodes, edges=edges), result_node


def run_analysis(
    session: Session,
    *,
    user: User,
    source: Any,
    other: Any | None,
    req: AnalysisRequest,
    introspect: Introspector,
    masked_source: frozenset[str],
    masked_other: frozenset[str],
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    base_uri: str,
    apply_ddl: Callable[[Session, str], None] | None = None,
) -> dict[str, Any]:
    """`source`/`other` = lignes Collection déjà autorisées en lecture par l'appelant (porte REST
    `get_collection_for_read`, comme /aggregate). Lève AnalysisError (422) ou PipelineRuntimeError."""
    info = hide_sensitive_columns(introspect(session, source.table_name), sorted(masked_source))
    other_info = (
        hide_sensitive_columns(introspect(session, other.table_name), sorted(masked_other))
        if other is not None
        else None
    )
    counts = [
        c for c in (source.feature_count, getattr(other, "feature_count", None)) if c is not None
    ]
    tool, args = _validate(req, info, other_info, max(counts) if counts else None)
    op_params = tool.op_params(args)
    out_srid = _srids(tool, op_params, info, other_info)

    if req.output == "collection":
        require_privilege(session, user, Privilege.DATA_MANAGE.value)
        geom_type = tool.out_geometry(info.geometry_type)
        if geom_type is None:
            raise AnalysisError(
                "type de géométrie de sortie indéterminé (couche source mixte) : sortie collection impossible"
            )
        keep = [
            c.name
            for c in _prop_columns(info)
            if c.type in _SQL_TYPE and c.name not in _RESERVED_COLUMNS
        ]
        keep = tool.keep(args, keep)
        by_name = {c.name: c for c in info.columns}
        columns = [
            EmptyCollectionColumn(name=n, sqlType=_SQL_TYPE[by_name[n].type])  # type: ignore[arg-type]
            for n in keep
        ] + [EmptyCollectionColumn(name=n, sqlType=t) for n, t in tool.added(args)]  # type: ignore[arg-type]
        assert apply_ddl is not None
        target = create_empty_collection(
            session,
            tenant_id=user.tenant_id,
            owner_id=user.id,
            title=req.title or "",
            columns=columns,
            geometry_type=geom_type,  # type: ignore[arg-type]
            srid=out_srid,
            introspect=introspect,
            apply_ddl=apply_ddl,
        )
        payload, _ = _payload(
            tool,
            op_params,
            req,
            source_id=source.id,
            out_srid=out_srid,
            keep_columns=[*keep, *[n for n, _t in tool.added(args)]],
            target_collection_id=target.id,
        )
        stats = run_pipeline(
            session,
            payload=payload,
            tenant_id=user.tenant_id,
            user=user,
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            base_uri=base_uri,
        )
        written = next(s.rowCount for s in stats if s.op == "writer.collection")
        session.execute(
            text("UPDATE collections SET feature_count = :n WHERE id = :id"),
            {"n": written, "id": target.id},
        )
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="analysis.run",
            object_type="collection",
            object_id=target.id,
            payload={
                "tool": tool.name,
                "source": source.id,
                "other": req.otherCollectionId,
                "rows": written,
            },
        )
        return {
            "tool": tool.name,
            "output": "collection",
            "collectionId": target.id,
            "rowCount": written,
            "srid": out_srid,
        }

    payload, last = _payload(
        tool,
        op_params,
        req,
        source_id=source.id,
        out_srid=out_srid,
        keep_columns=None,
        target_collection_id=None,
    )
    rows = preview_pipeline(
        session=session,
        payload=payload,
        tenant_id=user.tenant_id,
        user=user,
        up_to=last,
        endpoint_url=endpoint_url,
        access_key=access_key,
        secret_key=secret_key,
        base_uri=base_uri,
        limit=req.limit + 1,
    )
    truncated = len(rows) > req.limit
    features = []
    for row in rows[: req.limit]:
        geometry = row.pop("geometry", None)
        features.append({"type": "Feature", "geometry": geometry, "properties": row})
    return {
        "tool": tool.name,
        "output": "ephemeral",
        "srid": 4326,
        "truncated": truncated,
        "featureCollection": {"type": "FeatureCollection", "features": features},
    }


__all__ = [
    "TOOLS",
    "AnalysisError",
    "AnalysisRequest",
    "PipelineRuntimeError",
    "run_analysis",
    "tool_catalog",
]
