# SPDX-License-Identifier: Apache-2.0
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import (
    get_current_user,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
from app.db import get_session
from app.users.models import User
from app.users.repository import count_admins, list_users, set_admin, set_analyst

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


class MeResponse(BaseModel):
    id: str
    tenantId: str
    username: str
    email: str | None
    firstName: str
    lastName: str
    isAdmin: bool
    isAnalyst: bool
    capabilities: MeCapabilities


@router.get("/me", response_model=MeResponse)
def get_me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        tenantId=user.tenant_id,
        username=user.username,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        isAdmin=user.is_admin,
        isAnalyst=user.is_analyst,
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
        ),
    )


class UserAdminPatch(BaseModel):
    isAdmin: bool | None = None
    isAnalyst: bool | None = None


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _user_json(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "isAdmin": user.is_admin,
        "isAnalyst": user.is_analyst,
    }


@router.get("/users")
def get_users(
    page: int = 1,
    pageSize: int = 50,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_admin(user)
    users, total = list_users(session, tenant_id=user.tenant_id, page=page, page_size=pageSize)
    return {"users": [_user_json(u) for u in users], "total": total}


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserAdminPatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_admin(user)
    # Requête directe sur le modèle User autorisée ici : `auth` est au-dessus
    # de `users` dans le layering.
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if body.isAdmin is not None:
        if (
            not body.isAdmin
            and target.is_admin
            and count_admins(session, tenant_id=user.tenant_id) == 1
        ):
            raise HTTPException(status_code=409, detail="cannot demote the last admin")
        set_admin(session, tenant_id=user.tenant_id, user_id=user_id, is_admin=body.isAdmin)
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="user.promote" if body.isAdmin else "user.demote",
            object_type="user",
            object_id=user_id,
            payload={"isAdmin": body.isAdmin},
        )
    if body.isAnalyst is not None:
        set_analyst(session, tenant_id=user.tenant_id, user_id=user_id, is_analyst=body.isAnalyst)
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="user.grant_analyst" if body.isAnalyst else "user.revoke_analyst",
            object_type="user",
            object_id=user_id,
            payload={"isAnalyst": body.isAnalyst},
        )
    target = session.scalar(
        select(User).where(User.tenant_id == user.tenant_id, User.id == user_id)
    )
    if target is None:  # pragma: no cover - existence already proven above
        raise HTTPException(status_code=404, detail="user not found")
    return _user_json(target)
