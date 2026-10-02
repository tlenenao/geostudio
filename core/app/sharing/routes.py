# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import has_privilege, require_privilege, require_sharing_privilege
from app.roles.privileges import Privilege
from app.sharing import repository as repo
from app.users.models import User

router = APIRouter()


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RenameGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GroupRead(BaseModel):
    id: str
    name: str
    createdBy: str
    # j13-006 : l'appelant peut gérer les membres/renommer/supprimer (créateur
    # ou administrateur des utilisateurs) — le shell n'affiche que ce qui marchera.
    canManage: bool


class GroupMemberRead(BaseModel):
    userId: str
    username: str
    email: str | None


def _is_group_admin(session: Session, user: User) -> bool:
    return has_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)


def _group_read(group, *, user: User, as_admin: bool) -> GroupRead:
    return GroupRead(
        id=group.id,
        name=group.name,
        createdBy=group.created_by,
        canManage=as_admin or group.created_by == user.id,
    )


class AddMemberRequest(BaseModel):
    userId: str


@router.get("/groups", response_model=list[GroupRead])
def list_groups(
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[GroupRead]:
    # j02-005 : liste de tout le tenant, réservée à qui peut partager un kind
    # (consommateur : ShareForm) — un Lecteur n'y accède plus.
    require_sharing_privilege(session, user)
    as_admin = _is_group_admin(session, user)
    return [
        _group_read(g, user=user, as_admin=as_admin)
        for g in repo.list_groups(session, tenant_id=user.tenant_id)
    ]


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    body: CreateGroupRequest,
    session: Session = Depends(get_session, scope="function"),
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
    return _group_read(group, user=user, as_admin=False)


@router.post("/groups/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_member(
    group_id: str,
    body: AddMemberRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> Response:
    ok = repo.add_member(
        session,
        tenant_id=user.tenant_id,
        group_id=group_id,
        user_id=body.userId,
        caller_id=user.id,
        as_admin=_is_group_admin(session, user),
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


def _managed_group(session: Session, user: User, group_id: str):
    group = repo.get_managed_group(
        session,
        tenant_id=user.tenant_id,
        group_id=group_id,
        caller_id=user.id,
        as_admin=_is_group_admin(session, user),
    )
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


@router.get("/groups/{group_id}/members", response_model=list[GroupMemberRead])
def list_group_members(
    group_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[GroupMemberRead]:
    group = _managed_group(session, user, group_id)
    return [
        GroupMemberRead(userId=u.id, username=u.username, email=u.email)
        for u in repo.list_members(session, group=group)
    ]


@router.delete("/groups/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: str,
    member_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> Response:
    group = _managed_group(session, user, group_id)
    if not repo.remove_member(session, group=group, user_id=member_id):
        raise HTTPException(status_code=404, detail="member not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="group.remove_member",
        object_type="group",
        object_id=group_id,
        payload={"userId": member_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/groups/{group_id}", response_model=GroupRead)
def rename_group(
    group_id: str,
    body: RenameGroupRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> GroupRead:
    group = _managed_group(session, user, group_id)
    repo.rename_group(session, group=group, name=body.name)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="group.rename",
        object_type="group",
        object_id=group_id,
        payload={"name": body.name},
    )
    return _group_read(group, user=user, as_admin=_is_group_admin(session, user))


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> Response:
    group = _managed_group(session, user, group_id)
    repo.delete_group(session, group=group)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="group.delete",
        object_type="group",
        object_id=group_id,
        payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
