# SPDX-License-Identifier: Apache-2.0
"""Routes des relations entre collections (ARC-21, ADR 0021)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.routes import get_collection_for_read
from app.db import get_session
from app.features.routes import get_rls_scope
from app.relations import service
from app.relations.models import CollectionRelation
from app.relations.schemas import RelatedRecords, RelationCreate, RelationOut
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege

router = APIRouter()


def _out(rel: CollectionRelation) -> RelationOut:
    return RelationOut(
        id=rel.id,
        name=rel.name,
        cardinality=rel.cardinality,  # type: ignore[arg-type]
        parentCollectionId=rel.parent_collection_id,
        childCollectionId=rel.child_collection_id,
        parentKey=rel.parent_key,
        childKey=rel.child_key,
        linkCollectionId=rel.link_collection_id,
        linkParentKey=rel.link_parent_key,
        linkChildKey=rel.link_child_key,
        onDelete=rel.on_delete,  # type: ignore[arg-type]
    )


@router.post("/relations", status_code=201, response_model=RelationOut)
def create_relation(
    body: RelationCreate,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    return _out(service.create_relation(session, user, body))


@router.delete("/relations/{relation_id}", status_code=204)
def delete_relation(
    relation_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    rel = service.get_relation(session, user.tenant_id, relation_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="relation not found")
    service.delete_relation(session, user, rel)


@router.get("/collections/{collection_id}/relations", response_model=list[RelationOut])
def list_collection_relations(
    collection_id: str,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    """Relations touchant la collection ; celles dont un autre côté est illisible pour
    l'appelant sont omises (il n'en apprend pas l'existence)."""
    col = get_collection_for_read(session, user, collection_id)
    out = []
    for rel in service.relations_of(session, col.tenant_id, col.id):
        ids = {rel.parent_collection_id, rel.child_collection_id, rel.link_collection_id} - {None}
        try:
            for cid in ids:
                get_collection_for_read(session, user, cid)  # type: ignore[arg-type]
        except HTTPException:
            continue
        out.append(_out(rel))
    return out


@router.get(
    "/collections/{collection_id}/items/{fid}/related/{relation_id}",
    response_model=RelatedRecords,
)
def related_records(
    collection_id: str,
    fid: str,
    relation_id: str,
    direction: str | None = Query(None, description="children | parents (auto sauf auto-relation)"),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    rls=Depends(get_rls_scope),
):
    col = get_collection_for_read(session, user, collection_id)
    rel = service.get_relation(session, col.tenant_id, relation_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="relation not found")
    direction, dst, feats, total = service.related_records(
        session, user, rel, col, fid, direction=direction, limit=limit, offset=offset, rls=rls
    )
    return RelatedRecords(
        relation=_out(rel),
        direction=direction,  # type: ignore[arg-type]
        collectionId=dst.id,
        features=feats,
        numberReturned=len(feats),
        numberMatched=total,
    )
