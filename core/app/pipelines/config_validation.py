# SPDX-License-Identifier: Apache-2.0
"""Registers the real per-op node validators for kind="pipeline" configs
(see app.configs.pipeline_validation for why this indirection exists).
Imported for its side effect by app.main, the only layer allowed to know
about both app.pipelines and app.configs — mirrors
app.collections.dataset_validation exactly.

Boundary decision (design SP-15a, Global Constraints): only param SHAPE
(Pydantic) and referenced-collection existence/permission are checked here,
at save time. Bounded SQL expressions (filter.expr, derive.expr,
aggregate.metrics values) and transform.join.on column existence are only
checked at execution time (app.pipelines.expr_validation / runtime) — a bad
expression fails the run clearly, it never blocks saving the pipeline."""

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.pipeline_validation import register_pipeline_node_validator
from app.configs.schemas import PipelineNode
from app.pipelines.ops.schemas import BINARY_OPS, OP_PARAMS
from app.sharing.authorization import can
from app.users.models import User

_COLLECTION_PARAM_FIELD = {
    "reader.collection": "collectionId",
    "transform.join": "withCollectionId",
    "transform.intersection": "withCollectionId",
    "transform.countWithin": "withCollectionId",
    "transform.merge": "withCollectionId",
    "writer.collection": "collectionId",
    "writer.dataset": "collectionId",
}
_WRITE_OPS = {"writer.collection", "writer.dataset"}


def _validate_params(node: PipelineNode) -> BaseModel:
    model = OP_PARAMS.get(node.op)
    if model is None:
        raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
    try:
        return model.model_validate(node.params)
    except Exception as exc:  # pydantic.ValidationError, reported verbatim
        raise HTTPException(status_code=422, detail=f"{node.op}: {exc}") from exc


def _require_readable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session,
        tenant_id=user.tenant_id,
        collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    readable = can(
        session,
        user_id=user.id,
        action="read",
        item=collections_repo.get_access_facts(collection),
        kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        # Same message as not-found: don't leak collection existence.
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")


def _require_writable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session,
        tenant_id=user.tenant_id,
        collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    writable = can(
        session,
        user_id=user.id,
        action="write",
        item=collections_repo.get_access_facts(collection),
        kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not writable or not collection.editable:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' is not writable")


def _validate_node(session: Session, node: PipelineNode, edges: list, user: User) -> None:
    params = _validate_params(node)
    field = _COLLECTION_PARAM_FIELD.get(node.op)
    has_secondary_edge = any(e.to == node.id and e.role == "secondary" for e in edges)

    if node.op in BINARY_OPS:
        has_primary_edge = any(e.to == node.id and e.role != "secondary" for e in edges)
        if not has_primary_edge:
            raise HTTPException(
                status_code=422,
                detail=f"{node.op}: requires a primary input edge",
            )
        collection_id = getattr(params, field)
        if has_secondary_edge and collection_id is not None:
            raise HTTPException(
                status_code=422,
                detail=f"{node.op}: cannot have both '{field}' and a secondary input edge",
            )
        if not has_secondary_edge and collection_id is None:
            raise HTTPException(
                status_code=422,
                detail=f"{node.op}: requires either '{field}' or a secondary input edge",
            )
        if collection_id is not None:
            _require_readable_collection(session, user=user, collection_id=collection_id)
        return

    if has_secondary_edge:
        raise HTTPException(
            status_code=422,
            detail=f"{node.op}: does not accept a secondary input edge",
        )

    if field is None:
        return
    collection_id = getattr(params, field)
    if node.op in _WRITE_OPS:
        _require_writable_collection(session, user=user, collection_id=collection_id)
    else:
        _require_readable_collection(session, user=user, collection_id=collection_id)


for _op in OP_PARAMS:
    register_pipeline_node_validator(_op, _validate_node)
