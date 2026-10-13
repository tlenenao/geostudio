# SPDX-License-Identifier: Apache-2.0
"""GET /v1/{items|collections}/{id}/impact|lineage (ARC4-F15) — lecture seule, filtrée
par ce que l'utilisateur peut lire ; un objet illisible est indistinguable d'un absent."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.lineage import service
from app.lineage.service import NodeKey
from app.users.models import User

router = APIRouter()


class NodeRead(BaseModel):
    type: Literal["item", "collection"]
    id: str
    title: str
    resourceType: str


class DependentRead(NodeRead):
    depth: int  # 1 = dépendant direct
    direct: bool


class ImpactRead(BaseModel):
    target: NodeRead
    dependents: list[DependentRead]
    hiddenCount: int  # dépendants illisibles : comptés, jamais nommés


class LineageNodeRead(NodeRead):
    direction: Literal["upstream", "downstream"]


class NodeRef(BaseModel):
    type: Literal["item", "collection"]
    id: str


class EdgeRead(BaseModel):
    from_: NodeRef = Field(alias="from")  # « from utilise to »
    to: NodeRef

    model_config = {"populate_by_name": True}


class LineageRead(BaseModel):
    target: NodeRead
    nodes: list[LineageNodeRead]
    edges: list[EdgeRead]
    hiddenCount: int


def _resolve(session: Session, user: User, key: NodeKey) -> service.Graph:
    graph = service.build_graph(session, tenant_id=user.tenant_id)
    if key not in graph.titles or key not in service.visible_nodes(session, user, {key}):
        raise HTTPException(status_code=404, detail="not found")
    return graph


@router.get("/items/{item_id}/impact", response_model=ImpactRead)
def item_impact(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> dict:
    key: NodeKey = ("item", item_id)
    return service.impact(session, user, key, graph=_resolve(session, user, key))


@router.get("/items/{item_id}/lineage", response_model=LineageRead)
def item_lineage(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> dict:
    key: NodeKey = ("item", item_id)
    return service.lineage(session, user, key, graph=_resolve(session, user, key))


@router.get("/collections/{collection_id}/impact", response_model=ImpactRead)
def collection_impact(
    collection_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> dict:
    key: NodeKey = ("collection", collection_id)
    return service.impact(session, user, key, graph=_resolve(session, user, key))


@router.get("/collections/{collection_id}/lineage", response_model=LineageRead)
def collection_lineage(
    collection_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> dict:
    key: NodeKey = ("collection", collection_id)
    return service.lineage(session, user, key, graph=_resolve(session, user, key))
