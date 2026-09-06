# SPDX-License-Identifier: Apache-2.0
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import (
    get_current_user,
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_quotas_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import count_users_with_privileges, get_role, roles_for_ids
from app.tenants.models import Tenant
from app.users.models import User
from app.users.repository import list_users, set_user_role

router = APIRouter()


class MeCapabilities(BaseModel):
    """Les capacités du déploiement, servies avec le profil.

    Même contenu que `GET /instance`, qui reste servi sans authentification
    (page de connexion, mode démo). Le doublon est délibéré : le shell dérive
    l'état de ses domaines d'un profil unique (spec §6.6) au lieu de croiser
    deux requêtes dans chaque écran. `tests/test_auth_me_capabilities.py`
    interdit aux deux routes de diverger.
    """

    readOnly: bool
    etlEnabled: bool
    exportEnabled: bool
    appExportEnabled: bool
    tileset3dEnabled: bool
    terrain3dEnabled: bool
    copilotEnabled: bool
    adminToolsEnabled: bool
    quotasEnabled: bool


class RoleSummary(BaseModel):
    id: str
    name: str
    slug: str


class MeResponse(BaseModel):
    id: str
    tenantId: str
    tenantSlug: str
    username: str
    email: str | None
    firstName: str
    lastName: str
    role: RoleSummary
    privileges: list[str]
    version: str
    capabilities: MeCapabilities


@router.get("/me", response_model=MeResponse)
def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    tenant = session.get(Tenant, user.tenant_id)
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    # role_id est NOT NULL, jamais orphelin (suppression bloquée si en usage).
    assert role is not None
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        tenantSlug=tenant.slug if tenant is not None else user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        role=RoleSummary(id=role.id, name=role.name, slug=role.slug),
        privileges=role.privileges,
        version=request.app.version,
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
            adminToolsEnabled=is_admin_tools_enabled(),
            quotasEnabled=is_quotas_enabled(),
        ),
    )


class UserRolePatch(BaseModel):
    roleId: str


def _user_json(user: User, role_slug: str) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "roleSlug": role_slug}


@router.get("/users")
def get_users(
    page: int = 1,
    pageSize: int = 50,
    q: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    users, total = list_users(session, tenant_id=user.tenant_id, page=page, page_size=pageSize, q=q)
    # REV-085 : une seule requête pour l'ensemble des role_id de la page,
    # au lieu d'un get_role() par utilisateur (même patron que
    # roles_for_items/get_access_facts_by_ids).
    roles_by_id = roles_for_ids(
        session, tenant_id=user.tenant_id, role_ids=[u.role_id for u in users]
    )
    result = [
        _user_json(u, roles_by_id[u.role_id].slug if u.role_id in roles_by_id else "")
        for u in users
    ]
    return {"users": result, "total": total}


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserRolePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    new_role = get_role(session, tenant_id=user.tenant_id, role_id=body.roleId)
    if new_role is None:
        raise HTTPException(status_code=400, detail="role not found")
    needed = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]
    current_role = get_role(session, tenant_id=user.tenant_id, role_id=target.role_id)
    # Évalué privilège par privilège (SP-42/F-securite-autorisation-07) : une
    # précondition en conjonction sur les DEUX privilèges à la fois devient
    # inerte dès qu'ils vivent sur deux rôles distincts (cas normal avec des
    # rôles sur mesure granulaires). Chaque privilège anti-lockout est donc
    # protégé indépendamment, quel que soit le rôle qui le porte.
    if current_role is not None:
        for privilege in needed:
            if (
                privilege in current_role.privileges
                and privilege not in new_role.privileges
                and count_users_with_privileges(
                    session, tenant_id=user.tenant_id, privileges=[privilege]
                )
                == 1
            ):
                raise HTTPException(
                    status_code=409, detail="cannot leave the tenant without an admin"
                )
    set_user_role(
        session,
        tenant_id=user.tenant_id,
        user_id=user_id,
        role_id=body.roleId,
        role_slug=new_role.slug,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="user.role_change",
        object_type="user",
        object_id=user_id,
        payload={"roleId": body.roleId},
    )
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:  # pragma: no cover - existence already proven above
        raise HTTPException(status_code=404, detail="user not found")
    return _user_json(target, new_role.slug)
