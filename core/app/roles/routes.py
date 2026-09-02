# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.models import Role
from app.roles.privileges import ALL_PRIVILEGE_VALUES, Privilege
from app.roles.repository import (
    count_role_holders,
    create_role,
    delete_role,
    get_privilege_catalog,
    get_role,
    list_roles,
    update_role,
    would_orphan_privilege_holders,
)
from app.roles.schemas import PrivilegeCatalogEntry, RoleCreate, RolePatch, RoleRead
from app.users.models import User

router = APIRouter()

_ANTI_LOCKOUT_PRIVILEGES = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]


def _role_json(role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        name=role.name,
        slug=role.slug,
        isBuiltIn=role.is_built_in,
        privileges=role.privileges,
    )


@router.get("/roles/catalog", response_model=list[PrivilegeCatalogEntry])
def get_roles_catalog(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[PrivilegeCatalogEntry]:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    return [PrivilegeCatalogEntry(**entry) for entry in get_privilege_catalog()]


@router.get("/roles", response_model=list[RoleRead])
def get_roles(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[RoleRead]:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    return [_role_json(r) for r in list_roles(session, tenant_id=user.tenant_id)]


@router.post("/roles", response_model=RoleRead, status_code=201)
def post_role(
    body: RoleCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoleRead:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    unknown = set(body.privileges) - set(ALL_PRIVILEGE_VALUES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown privileges: {sorted(unknown)}")
    role = create_role(
        session, tenant_id=user.tenant_id, name=body.name, privileges=body.privileges
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="role.create",
        object_type="role",
        object_id=role.id,
        payload={"name": role.name, "privileges": role.privileges},
    )
    return _role_json(role)


@router.patch("/roles/{role_id}", response_model=RoleRead)
def patch_role(
    role_id: str,
    body: RolePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoleRead:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    role = get_role(session, tenant_id=user.tenant_id, role_id=role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    if role.is_built_in:
        raise HTTPException(status_code=400, detail="a built-in role cannot be edited")
    if body.privileges is not None:
        unknown = set(body.privileges) - set(ALL_PRIVILEGE_VALUES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown privileges: {sorted(unknown)}")
        if set(_ANTI_LOCKOUT_PRIVILEGES).issubset(
            set(role.privileges)
        ) and would_orphan_privilege_holders(
            session,
            tenant_id=user.tenant_id,
            privileges=_ANTI_LOCKOUT_PRIVILEGES,
            role_id=role.id,
            new_privileges=body.privileges,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "this change would leave the tenant without anyone able to manage users/roles"
                ),
            )
    updated = update_role(
        session,
        tenant_id=user.tenant_id,
        role_id=role_id,
        name=body.name,
        privileges=body.privileges,
    )
    if updated is None:  # pragma: no cover - existence already proven above
        raise HTTPException(status_code=404, detail="role not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="role.update",
        object_type="role",
        object_id=role_id,
        payload={"name": body.name, "privileges": body.privileges},
    )
    return _role_json(updated)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role_route(
    role_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    require_privilege(session, user, Privilege.ADMIN_ROLES_MANAGE.value)
    role = get_role(session, tenant_id=user.tenant_id, role_id=role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    if role.is_built_in:
        raise HTTPException(status_code=400, detail="a built-in role cannot be deleted")
    holders = count_role_holders(session, tenant_id=user.tenant_id, role_id=role_id)
    if holders > 0:
        raise HTTPException(status_code=409, detail=f"{holders} user(s) still have this role")
    delete_role(session, tenant_id=user.tenant_id, role_id=role_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="role.delete",
        object_type="role",
        object_id=role_id,
        payload={},
    )
