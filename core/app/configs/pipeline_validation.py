# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="pipeline" payloads without
importing app.pipelines (forbidden by the layered-architecture contract:
app.pipelines sits above app.configs). Structural graph checks (DAG
acyclic, linear+join topology — feasibility study §4.1 mitigation D1) live
here: they need no knowledge of the op catalogue. Per-node checks (op
exists, params match its manifest, collectionId exists/readable/writable)
are registered by app.pipelines.config_validation, imported for its side
effect by app.main — the only layer allowed to know about both. Mirrors
app.configs.dataset_validation exactly."""

from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig, PipelineEdge, PipelineNode
from app.users.models import User

NodeValidator = Callable[[Session, PipelineNode, list[PipelineEdge], User], None]

_node_validators: dict[str, NodeValidator] = {}


def register_pipeline_node_validator(op: str, validator: NodeValidator) -> None:
    _node_validators[op] = validator


def _check_topology(edges: list[PipelineEdge]) -> None:
    primary_count: dict[str, int] = {}
    secondary_count: dict[str, int] = {}
    for edge in edges:
        bucket = secondary_count if edge.role == "secondary" else primary_count
        bucket[edge.to] = bucket.get(edge.to, 0) + 1
    for node_id, count in primary_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one incoming edge "
                "(linear+join topology only, SP-15a MVP)",
            )
    for node_id, count in secondary_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one secondary incoming edge",
            )


def _check_acyclic(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> None:
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def visit(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and visit(neighbor):
                return True
        color[node_id] = BLACK
        return False

    if any(color[n.id] == WHITE and visit(n.id) for n in nodes):
        raise HTTPException(status_code=422, detail="pipeline graph must be acyclic")


def validate_pipeline_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "pipeline":
        return
    payload = config.pipeline
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    _check_acyclic(payload.nodes, payload.edges)
    _check_topology(payload.edges)

    for node in payload.nodes:
        validator = _node_validators.get(node.op)
        if validator is None:
            raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
        validator(session, node, payload.edges, user)
