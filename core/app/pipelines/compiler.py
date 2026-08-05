# SPDX-License-Identifier: Apache-2.0
"""Compilateur DAG→SQL du runtime étage 1 (design SP-15a §6.1). Topologie
linéaire+join uniquement (Global Constraints de ce plan — feasibility study
§4.1 D1) : chaque nœud a au plus une arête entrante, le second flux de
transform.join est un PARAM (withCollectionId), jamais une seconde arête.
Pas de fusion : compile_transform_sql produit UN fragment SQL par nœud
transform, exécuté comme sa propre TEMP VIEW par le runtime (Task 8) — ce
module ne touche jamais une connexion DuckDB, il ne fait que construire des
chaînes de caractères, testable en pur."""
from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformDeriveParams, TransformFilterParams,
    TransformJoinParams, TransformSelectParams,
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
    incoming = [e.from_ for e in edges if e.to == node_id]
    if len(incoming) > 1:
        raise ValueError(
            f"node '{node_id}' has more than one incoming edge "
            "(linear+join topology only, SP-15a MVP)"
        )
    return incoming[0] if incoming else None


def compile_transform_sql(
    op: str, params: dict, *, input_view: str, join_view: str | None = None,
) -> str:
    if op == "transform.filter":
        p = TransformFilterParams.model_validate(params)
        return f"SELECT * FROM {_qi(input_view)} WHERE ({p.expr})"

    if op == "transform.select":
        p = TransformSelectParams.model_validate(params)
        cols = ", ".join(
            f"{_qi(src)} AS {_qi(dst)}" if dst else _qi(src)
            for src, dst in p.columns.items()
        )
        return f"SELECT {cols} FROM {_qi(input_view)}"

    if op == "transform.derive":
        p = TransformDeriveParams.model_validate(params)
        return f"SELECT *, ({p.expr}) AS {_qi(p.column)} FROM {_qi(input_view)}"

    if op == "transform.aggregate":
        p = TransformAggregateParams.model_validate(params)
        group_cols = ", ".join(_qi(c) for c in p.groupBy)
        metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
        select_cols = ", ".join(filter(None, [group_cols, metric_cols]))
        group_clause = f" GROUP BY {group_cols}" if group_cols else ""
        return f"SELECT {select_cols} FROM {_qi(input_view)}{group_clause}"

    if op == "transform.join":
        p = TransformJoinParams.model_validate(params)
        assert join_view is not None, "transform.join requires join_view"
        join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
        return (
            f"SELECT * FROM {_qi(input_view)} {join_kw} {_qi(join_view)} "
            f"USING ({_qi(p.on)})"
        )

    raise ValueError(f"'{op}' is not a transform op")
