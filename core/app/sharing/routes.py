# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.sharing import repository as repo
from app.users.models import User

router = APIRouter()


class CreateGroupRequest(BaseModel):
    name: str


class GroupRead(BaseModel):
    id: str
    name: str


class AddMemberRequest(BaseModel):
    userId: str


@router.get("/groups", response_model=list[GroupRead])
def list_groups(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[GroupRead]:
    # REV-009 : décision explicite (le backlog demandait de trancher) — GET
    # /groups reste une liste de TOUT le tenant, pas seulement les groupes
    # dont l'appelant est créateur/membre. C'est déjà le contrat actuel
    # (repo.list_groups filtre uniquement par tenant_id) et le seul
    # consommateur de production (ShareForm.tsx, sélection de groupe pour un
    # partage) a besoin de voir tous les groupes du tenant pour y ajouter un
    # item/une collection — restreindre à créateur/membre casserait ce flux.
    return [
        GroupRead(id=g.id, name=g.name) for g in repo.list_groups(session, tenant_id=user.tenant_id)
    ]


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    body: CreateGroupRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupRead:
    # REV-009 : cette route ne consultait jusqu'ici que get_current_user —
    # aucun privilège — un Lecteur (0 privilège) pouvait créer des groupes
    # dans le tenant. Rattachée à catalog.manage : les groupes n'existent
    # que pour partager des items/collections, déjà gardés par ce privilège
    # à leur propre création.
    require_privilege(session, user, Privilege.CATALOG_MANAGE.value)
    group = repo.create_group(session, tenant_id=user.tenant_id, name=body.name, created_by=user.id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="group.create",
        object_type="group",
        object_id=group.id,
        payload={"name": body.name},
    )
    return GroupRead(id=group.id, name=group.name)


@router.post("/groups/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_member(
    group_id: str,
    body: AddMemberRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    ok = repo.add_member(
        session,
        tenant_id=user.tenant_id,
        group_id=group_id,
        user_id=body.userId,
        caller_id=user.id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="group or user not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="group.add_member",
        object_type="group",
        object_id=group_id,
        payload={"userId": body.userId},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
