# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.apikeys import service
from app.apikeys.models import ApiKey
from app.apikeys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.auth.dependency import forbid_api_key, get_current_user
from app.db import get_session
from app.roles.guards import has_privilege, require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()


def _iso(value: datetime | None) -> str | None:
    # Base : UTC naïf ; "Z" explicite pour que le navigateur ne le lise pas en local.
    return value.isoformat() + "Z" if value else None


def _read(key: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=key.id,
        name=key.name,
        prefix=key.key_prefix,
        createdAt=_iso(key.created_at) or "",
        expiresAt=_iso(key.expires_at) or "",
        revokedAt=_iso(key.revoked_at),
        lastUsedAt=_iso(key.last_used_at),
        scopes=key.scopes,
        readOnly=key.read_only,
    )


@router.get("/api-keys", response_model=list[ApiKeyRead], dependencies=[Depends(forbid_api_key)])
def list_keys(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> list[ApiKeyRead]:
    return [_read(k) for k in service.list_api_keys(session, user=user)]


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
    dependencies=[Depends(forbid_api_key)],
)
def create_key(
    body: ApiKeyCreate,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> ApiKeyCreated:
    if body.scopes is not None:  # AUD-091 : jamais au-delà des privilèges du créateur
        known = {p.value for p in Privilege}
        if unknown := sorted(set(body.scopes) - known):
            raise HTTPException(422, f"unknown privileges: {', '.join(unknown)}")
        if missing := sorted(p for p in set(body.scopes) if not has_privilege(session, user, p)):
            raise HTTPException(403, f"privileges not held: {', '.join(missing)}")
    key, token = service.create_api_key(
        session,
        user=user,
        name=body.name,
        expires_in_days=body.expiresInDays,
        scopes=body.scopes,
        read_only=body.readOnly,
    )
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyCreated(**_read(key).model_dump(), token=token)


@router.delete(
    "/api-keys/{key_id}", response_model=ApiKeyRead, dependencies=[Depends(forbid_api_key)]
)
def revoke_key(
    key_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> ApiKeyRead:
    key = service.revoke_api_key(session, user=user, key_id=key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="api key not found")
    return _read(key)


# REV-366 : un admin liste/révoque les clés d'un autre compte (agent parti, compte compromis).
# Réservé à une session interactive, comme la gestion de ses propres clés.
@router.get(
    "/admin/api-keys", response_model=list[ApiKeyRead], dependencies=[Depends(forbid_api_key)]
)
def admin_list_keys(
    user_id: str = Query(alias="user", min_length=1),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> list[ApiKeyRead]:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    return [_read(k) for k in service.list_api_keys(session, user=user, created_by=user_id)]


@router.delete(
    "/admin/api-keys/{key_id}", response_model=ApiKeyRead, dependencies=[Depends(forbid_api_key)]
)
def admin_revoke_key(
    key_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> ApiKeyRead:
    require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    key = service.revoke_api_key(session, user=user, key_id=key_id, any_owner=True)
    if key is None:
        raise HTTPException(status_code=404, detail="api key not found")
    return _read(key)
