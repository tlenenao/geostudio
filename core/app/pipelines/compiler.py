# SPDX-License-Identifier: Apache-2.0
"""Compilateur DAG→SQL du runtime étage 1 (design SP-15a §6.1). Topologie
linéaire+join uniquement (Global Constraints de ce plan — feasibility study
§4.1 D1) : chaque nœud a au plus une arête entrante, le second flux de
transform.join est un PARAM (withCollectionId), jamais une seconde arête.
Pas de fusion : compile_transform_sql produit UN fragment SQL par nœud
transform, exécuté comme sa propre TEMP VIEW par le runtime (Task 8) — ce
module ne touche jamais une connexion DuckDB, il ne fait que construire des
chaînes de caractères, testable en pur."""

from collections.abc import Callable

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.ops.schemas import (
    TransformAggregateParams,
    TransformBufferParams,
    TransformCountWithinParams,
    TransformDeriveParams,
    TransformFilterParams,
    TransformH3AggregateParams,
    TransformIntersectionParams,
    TransformJoinParams,
    TransformMergeParams,
    TransformQgisParams,
    TransformReprojectParams,
    TransformSelectParams,
)


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def topological_order(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> list[PipelineNode]:
    by_id = {n.id: n for n in nodes}
    indegree = {n.id: 0 for n in nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)
        indegree[edge.to] += 1

    queue = sorted(n.id for n in nodes if indegree[n.id] == 0)
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        newly_ready = []
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                newly_ready.append(neighbor)
        queue = sorted(queue + newly_ready)

    if len(ordered) != len(nodes):
        raise ValueError("pipeline graph must be acyclic")
    return [by_id[i] for i in ordered]


def predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    incoming = [e.from_ for e in edges if e.to == node_id and e.role != "secondary"]
    if len(incoming) > 1:
        raise ValueError(
            f"node '{node_id}' has more than one incoming edge "
            "(linear+join topology only, SP-15a MVP)"
        )
    return incoming[0] if incoming else None


def secondary_predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    """Résout la seconde entrée (SP-15g §3.1) d'un op binaire — l'alternative
    additive à son paramètre `withCollectionId`. Ignoré pour tout autre op
    (une arête secondaire y est de toute façon rejetée à la sauvegarde,
    app.pipelines.config_validation)."""
    incoming = [e.from_ for e in edges if e.to == node_id and e.role == "secondary"]
    if len(incoming) > 1:
        raise ValueError(f"node '{node_id}' has more than one secondary incoming edge")
    return incoming[0] if incoming else None


def _compile_filter(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformFilterParams.model_validate(params)
    return f"SELECT * FROM {_qi(input_view)} WHERE ({p.expr})"


def _compile_select(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformSelectParams.model_validate(params)
    cols = ", ".join(
        f"{_qi(src)} AS {_qi(dst)}" if dst else _qi(src) for src, dst in p.columns.items()
    )
    return f"SELECT {cols} FROM {_qi(input_view)}"


def _compile_derive(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformDeriveParams.model_validate(params)
    return f"SELECT *, ({p.expr}) AS {_qi(p.column)} FROM {_qi(input_view)}"


def _compile_aggregate(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformAggregateParams.model_validate(params)
    group_cols = ", ".join(_qi(c) for c in p.groupBy)
    metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
    select_cols = ", ".join(filter(None, [group_cols, metric_cols]))
    group_clause = f" GROUP BY {group_cols}" if group_cols else ""
    return f"SELECT {select_cols} FROM {_qi(input_view)}{group_clause}"


def _compile_join(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformJoinParams.model_validate(params)
    assert join_view is not None, "transform.join requires join_view"
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    return f"SELECT * FROM {_qi(input_view)} {join_kw} {_qi(join_view)} USING ({_qi(p.on)})"


def _compile_buffer(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformBufferParams.model_validate(params)
    if p.unit == "native":
        return (
            f"SELECT * EXCLUDE (geometry), ST_Buffer(geometry, {p.distance}) AS geometry "
            f"FROM {_qi(input_view)}"
        )
    assert input_srid is not None, "transform.buffer(unit='meters') requires input_srid"
    # always_xy=true est obligatoire ici : cf. plan Global Constraints
    # (sans lui, ST_Transform applique l'ordre d'axe EPSG (lat,lng) pour
    # EPSG:4326 et intervertit x/y silencieusement — vérifié contre un
    # DuckDB réel).
    src = f"'EPSG:{input_srid}'"
    return (
        f"SELECT * EXCLUDE (geometry), "
        f"ST_Transform(ST_Buffer(ST_Transform(geometry, {src}, 'EPSG:3857', true), "
        f"{p.distance}), 'EPSG:3857', {src}, true) AS geometry FROM {_qi(input_view)}"
    )


def _compile_reproject(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformReprojectParams.model_validate(params)
    assert input_srid is not None, "transform.reproject requires input_srid"
    return (
        f"SELECT * EXCLUDE (geometry), "
        f"ST_Transform(geometry, 'EPSG:{input_srid}', '{p.targetCrs}', true) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_intersection(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformIntersectionParams.model_validate(params)
    assert join_view is not None, "transform.intersection requires join_view"
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    geom_expr = (
        "t.geometry" if p.outputGeometry == "left" else "ST_Intersection(t.geometry, o.geometry)"
    )
    return (
        f"SELECT t.* EXCLUDE (geometry), {geom_expr} AS geometry "
        f"FROM {_qi(input_view)} t {join_kw} {_qi(join_view)} o "
        f"ON ST_Intersects(t.geometry, o.geometry)"
    )


def _compile_count_within(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformCountWithinParams.model_validate(params)
    assert join_view is not None, "transform.countWithin requires join_view"
    if p.predicate == "intersects":
        predicate_expr = "ST_Intersects(t.geometry, o.geometry)"
    else:  # contains
        predicate_expr = "ST_Contains(o.geometry, t.geometry)"
    return (
        f"SELECT t.* EXCLUDE (geometry), t.geometry, COUNT(o.geometry) AS {_qi(p.countColumn)} "
        f"FROM {_qi(input_view)} t LEFT JOIN {_qi(join_view)} o "
        f"ON {predicate_expr} GROUP BY ALL"
    )


def _compile_h3_aggregate(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformH3AggregateParams.model_validate(params)
    h3_expr = (
        f"h3_latlng_to_cell(ST_Y(ST_Centroid(geometry)), "
        f"ST_X(ST_Centroid(geometry)), {p.resolution})"
    )
    select_parts = [
        f"{h3_expr} AS h3Cell",
        f"ST_GeomFromText(h3_cell_to_boundary_wkt({h3_expr})) AS geometry",
    ]
    metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
    if metric_cols:
        select_parts.append(metric_cols)
    return f"SELECT {', '.join(select_parts)} FROM {_qi(input_view)} GROUP BY h3Cell"


def _compile_merge(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformMergeParams.model_validate(params)  # forme seulement, aucun autre champ à lire
    assert join_view is not None, "transform.merge requires join_view"
    return f"SELECT * FROM {_qi(input_view)} UNION ALL BY NAME SELECT * FROM {_qi(join_view)}"


_TRANSFORM_COMPILERS: dict[str, Callable[..., str]] = {
    "transform.filter": _compile_filter,
    "transform.select": _compile_select,
    "transform.derive": _compile_derive,
    "transform.aggregate": _compile_aggregate,
    "transform.join": _compile_join,
    "transform.buffer": _compile_buffer,
    "transform.reproject": _compile_reproject,
    "transform.intersection": _compile_intersection,
    "transform.countWithin": _compile_count_within,
    "transform.h3Aggregate": _compile_h3_aggregate,
    "transform.merge": _compile_merge,
}


def compile_transform_sql(
    op: str,
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    compiler_fn = _TRANSFORM_COMPILERS.get(op)
    if compiler_fn is None:
        raise ValueError(f"'{op}' is not a transform op")
    return compiler_fn(params, input_view=input_view, join_view=join_view, input_srid=input_srid)


def _output_srid_reproject(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    p = TransformReprojectParams.model_validate(params)
    return int(p.targetCrs.rsplit(":", 1)[1])


def _output_srid_reconcile_join(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    assert join_srid is not None, f"{op} requires join_srid"
    if input_srid != join_srid:
        raise ValueError(
            f"'{op}': input CRS (EPSG:{input_srid}) and joined collection CRS "
            f"(EPSG:{join_srid}) differ — insert transform.reproject first"
        )
    return input_srid


def _output_srid_h3_aggregate(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    if input_srid != 4326:
        raise ValueError(
            f"'transform.h3Aggregate' requires EPSG:4326 input (got EPSG:{input_srid}) "
            "— insert transform.reproject first"
        )
    return 4326


def _output_srid_qgis(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    p = TransformQgisParams.model_validate(params)
    return int(p.outputSrid.rsplit(":", 1)[1]) if p.outputSrid is not None else input_srid


_TRANSFORM_OUTPUT_SRID: dict[str, Callable[..., int]] = {
    "transform.reproject": _output_srid_reproject,
    "transform.intersection": _output_srid_reconcile_join,
    "transform.countWithin": _output_srid_reconcile_join,
    "transform.merge": _output_srid_reconcile_join,
    "transform.h3Aggregate": _output_srid_h3_aggregate,
    "transform.qgis": _output_srid_qgis,
}


def transform_output_srid(
    op: str,
    params: dict,
    *,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    """SRID de sortie d'un nœud transform, calculé sans connexion DuckDB
    (pur, comme compile_transform_sql). Lève ValueError si les deux entrées
    d'une op spatiale binaire ne partagent pas le même CRS — design §2/§3.3/
    §3.4/§3.5 : aucune réconciliation implicite, jamais un résultat spatial
    silencieusement faux. runtime.py convertit ce ValueError en
    PipelineRuntimeError avant de le laisser remonter."""
    output_srid_fn = _TRANSFORM_OUTPUT_SRID.get(op)
    if output_srid_fn is None:
        return input_srid  # passthrough — comportement déjà existant : pas
        # de branche d'erreur pour un op inconnu, contrairement à
        # compile_transform_sql (vérifié dans le code réel avant ce plan).
    return output_srid_fn(params, op=op, input_srid=input_srid, join_srid=join_srid)
