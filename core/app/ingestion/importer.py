# SPDX-License-Identifier: Apache-2.0
"""Pipeline d'import (SP-6a) : table PostGIS + collection + item carte, à
partir d'un flux de (géométrie, propriétés) déjà parsé (app.ingestion.parsers).
Séparé de tasks.py pour rester testable sans procrastinate ni S3 (postgis
seulement) — mêmes fonctions internes qu'un admin enregistrant une collection
à la main (app.collections.routes.register_collection)."""

import math
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.ddl import apply_collection_ddl
from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapLayer, MapView
from app.ingestion.parsers import (
    GeometryMode,
    IngestionParseError,
    _is_geoparquet,
    _temp_file,
    parse_csv_latlon,
    parse_geojson,
    parse_geoparquet,
    parse_gml,
    parse_gpkg,
    parse_jsonlines,
    parse_kml,
    parse_parquet_tabular,
    parse_shapefile_zip,
    parse_xlsx_sheet,
    parse_xml_generic,
)
from app.items import repository as items_repo
from app.sql_ident import quote_ident

# Doit rester synchronisé avec shell/src/map/basemaps.ts DEFAULT_BASEMAP.style.
_DEFAULT_BASEMAP_STYLE = "https://demotiles.maplibre.org/style.json"

_GEOM_TYPE_MAP = {
    "Point": "Point",
    "MultiPoint": "MultiPoint",
    "LineString": "LineString",
    "MultiLineString": "MultiLineString",
    "Polygon": "Polygon",
    "MultiPolygon": "MultiPolygon",
}


@dataclass
class ImportResult:
    collection_id: str
    item_id: str | None


def _resolve_geometry_mode(
    *,
    lat_field: str | None,
    lon_field: str | None,
    wkt_field: str | None,
    geometry_mode: str | None,
) -> GeometryMode:
    if geometry_mode == "wkt":
        return GeometryMode(kind="wkt", wkt_field=wkt_field)
    if geometry_mode == "none":
        return GeometryMode(kind="none")
    return GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)


def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".gpkg"):
        return "gpkg"
    if lower.endswith(".zip"):
        return "shapefile"
    if lower.endswith((".kml", ".kmz")):
        return "kml"
    if lower.endswith(".gml"):
        return "gml"
    if lower.endswith(".jsonl"):
        return "jsonlines"
    if lower.endswith(".xml"):
        return "xml_generic"
    if lower.endswith(".parquet"):
        return "parquet"  # désambiguïsé par contenu, cf. run_import
    raise IngestionParseError(f"format non supporté : {filename}")


def _sql_type_for(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "bigint"
    if isinstance(value, float):
        return "double precision"
    return "text"


def _zoom_for_extent(bbox: list[float]) -> float:
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.0001)
    # Approximation grossière (span=360° → zoom 0, chaque doublement du zoom
    # réduit le span de moitié) : suffisant pour un centrage initial
    # raisonnable, l'utilisateur ajuste ensuite dans l'éditeur de carte.
    return max(0.0, min(18.0, math.log2(360.0 / span)))


def run_import(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    filename: str,
    content: bytes,
    collection_title: str,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None = None,
    wkt_field: str | None = None,
    geometry_mode: str | None = None,
) -> ImportResult:
    mode = _resolve_geometry_mode(
        lat_field=lat_field, lon_field=lon_field, wkt_field=wkt_field, geometry_mode=geometry_mode
    )
    fmt = _pick_format(filename)
    if fmt == "geojson":
        rows = list(parse_geojson(content))
    elif fmt == "csv":
        rows = list(parse_csv_latlon(content, mode))
    elif fmt == "xlsx":
        rows = list(parse_xlsx_sheet(content, layer_name, mode))
    elif fmt == "gpkg":
        rows = list(parse_gpkg(content, layer_name))
    elif fmt == "shapefile":
        rows = list(parse_shapefile_zip(content, layer_name))
    elif fmt == "kml":
        rows = list(parse_kml(content, layer_name))
    elif fmt == "gml":
        rows = list(parse_gml(content, layer_name))
    elif fmt == "jsonlines":
        rows = list(parse_jsonlines(content, mode))
    elif fmt == "xml_generic":
        rows = list(parse_xml_generic(content, mode))
    elif fmt == "parquet":
        with _temp_file(content, ".parquet") as tmp_path:
            is_geo = _is_geoparquet(tmp_path)
        rows = (
            list(parse_geoparquet(content))
            if is_geo
            else list(parse_parquet_tabular(content, mode))
        )
    else:  # pragma: no cover — jamais atteint, _pick_format lève avant
        raise IngestionParseError(f"format non supporté : {filename}")
    if not rows:
        raise IngestionParseError("le fichier ne contient aucune entité")

    # Colonnes : union des clés de propriétés rencontrées, type déduit de la
    # première valeur non nulle vue pour chaque clé (repli "text" si toujours
    # nulle). Propriétés nommées "id" ou "geom" entreraient en collision avec
    # les colonnes fixes ci-dessous — cas non géré en v1 (hors périmètre SP-6a).
    columns: dict[str, str] = {}
    for _geom, props in rows:
        for key, value in props.items():
            if key in columns or value is None:
                continue
            columns[key] = _sql_type_for(value)
    for _geom, props in rows:
        for key in props:
            columns.setdefault(key, "text")

    # has_geometry : un seul mode de géométrie par import (jamais mixte, cf.
    # _resolve_geometry_mode/extract_geometry) — soit toutes les lignes
    # portent une géométrie, soit aucune (geometry_mode="none").
    has_geometry = any(geom is not None for geom, _props in rows)

    geom_types = {geom.geom_type for geom, _props in rows if geom is not None}
    single_type = next(iter(geom_types)) if len(geom_types) == 1 else None
    pg_geom_type = _GEOM_TYPE_MAP.get(single_type, "Geometry") if single_type else "Geometry"

    table_name = f"ingest_{uuid.uuid4().hex[:12]}"
    t = quote_ident(session, table_name)
    col_defs = ", ".join(
        f"{quote_ident(session, name)} {sql_type}" for name, sql_type in columns.items()
    )
    # tenant_id est déclaré ici (et rempli à l'INSERT) plutôt que laissé à
    # apply_collection_ddl ci-dessous : ce dernier ne fait qu'un
    # ADD COLUMN IF NOT EXISTS ... DEFAULT 'default' (no-op si la colonne
    # existe déjà) — s'il posait la colonne après coup, les lignes qu'on
    # vient d'insérer hériteraient toutes du littéral 'default' au lieu du
    # tenant réel de l'uploader, les rendant invisibles à travers RLS pour
    # tout tenant dont l'id n'est pas "default" (bug de cloisonnement).
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL"
    if col_defs:
        create_sql += f", {col_defs}"
    if has_geometry:
        create_sql += f", geom geometry({pg_geom_type}, 4326))"
    else:
        create_sql += ")"
    session.execute(text(create_sql))

    col_names = list(columns.keys())
    insert_cols = ", ".join(quote_ident(session, name) for name in col_names)
    if has_geometry:
        insert_cols_full = "tenant_id, " + (insert_cols + ", " if insert_cols else "") + "geom"
    else:
        insert_cols_full = "tenant_id" + (", " + insert_cols if insert_cols else "")
    placeholders = ", ".join(f":{name}" for name in col_names)
    if has_geometry:
        values_clause = (
            ":tenant_id, "
            + (placeholders + ", " if placeholders else "")
            + "ST_GeomFromText(:geom_wkt, 4326)"
        )
    else:
        values_clause = ":tenant_id" + (", " + placeholders if placeholders else "")
    insert_sql = f"INSERT INTO public.{t} ({insert_cols_full}) VALUES ({values_clause})"
    params = []
    for geom, props in rows:
        row_params = {name: props.get(name) for name in col_names}
        row_params["tenant_id"] = tenant_id
        if has_geometry:
            # has_geometry vrai => geom non-None sur toute ligne (mode
            # unique par import, cf. commentaire ci-dessus) : geom.wkt ne
            # lève jamais AttributeError sur None dans cette branche.
            row_params["geom_wkt"] = geom.wkt if geom is not None else None
        params.append(row_params)
    session.execute(text(insert_sql), params)

    info = introspect_table(session, table_name)
    apply_collection_ddl(session, table_name, tenant_id=tenant_id)
    col = collections_repo.create_collection(
        session,
        tenant_id=tenant_id,
        owner_id=created_by,
        table_name=table_name,
        title=collection_title,
        description="",
        is_public=False,
        pk_column=info.pk_column,
        geometry_column=info.geometry_column,
        geometry_type=info.geometry_type,
        srid=info.srid,
        feature_count=len(rows),
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=created_by,
        actor_kind="user",
        action="collection.create",
        object_type="collection",
        object_id=col.id,
        payload={"tableName": col.table_name},
    )

    if not has_geometry:
        # Pas de géométrie => pas de carte à afficher : aucun Item/Config
        # créé (JSON Lines/Parquet/XML génériques en geometry_mode="none",
        # GAP-29 Task 11) — seule la collection tabulaire existe.
        return ImportResult(collection_id=col.id, item_id=None)

    bbox = table_extent(session, info)
    if bbox:
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        zoom = _zoom_for_extent(bbox)
    else:
        center, zoom = (2.4, 46.6), 5.0

    # /v1 explicite : cette URL est écrite telle quelle dans MapLayer.url et
    # fetchée directement par le navigateur (shell/src/map/MapView.tsx,
    # data: layer.url) — jamais recomposée depuis coreUrl côté shell.
    # isHostedCoreUrl() (même fichier) compare cette URL au coreUrl versionné
    # du shell pour décider d'attacher le jeton d'auth (piège SP-24 C1) ;
    # sans /v1 ici, une collection non publique redeviendrait illisible.
    core_base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200") + "/v1"
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=created_by,
        resource_type="map",
        title=collection_title,
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=created_by,
        actor_kind="user",
        action="item.create",
        object_type="item",
        object_id=item.id,
        payload={"title": collection_title},
    )
    config = BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style=_DEFAULT_BASEMAP_STYLE),
            view=MapView(center=center, zoom=zoom),
            layers=[
                MapLayer(
                    id=str(uuid.uuid4()),
                    title=collection_title,
                    visible=True,
                    kind="feature",
                    url=f"{core_base_url}/collections/{col.id}/items",
                )
            ],
        ),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)

    return ImportResult(collection_id=col.id, item_id=item.id)
