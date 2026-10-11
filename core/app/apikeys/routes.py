# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.apikeys import service
from app.apikeys.models import ApiKey
from app.apikeys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.auth.dependency import get_current_user
from app.db import get_session
from app.users.models import User

router = APIRouter()


def get_interactive_user(
    authorization: str = Header(default=""),
    user: User = Depends(get_current_user),
) -> User:
    """Gestion des clés réservée à une session interactive : une clé ne crée
    ni ne révoque de clés (sinon elle survivrait à sa propre révocation)."""
    if service.is_api_key(authorization.removeprefix("Bearer ")):
        raise HTTPException(status_code=403, detail="api keys cannot manage api keys")
    return user


def _read(key: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=key.id,
        name=key.name,
        prefix=key.key_prefix,
        createdAt=key.created_at.isoformat(),
        expiresAt=key.expires_at.isoformat(),
        revokedAt=key.revoked_at.isoformat() if key.revoked_at else None,
        lastUsedAt=key.last_used_at.isoformat() if key.last_used_at else None,
    )


@router.get("/api-keys", response_model=list[ApiKeyRead])
def list_keys(
    user: User = Depends(get_interactive_user),
    session: Session = Depends(get_session, scope="function"),
) -> list[ApiKeyRead]:
    return [_read(k) for k in service.list_api_keys(session, user=user)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(
    body: ApiKeyCreate,
    response: Response,
    user: User = Depends(get_interactive_user),
    session: Session = Depends(get_session, scope="function"),
) -> ApiKeyCreated:
    key, token = service.create_api_key(
        session, user=user, name=body.name, expires_in_days=body.expiresInDays
    )
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyCreated(**_read(key).model_dump(), token=token)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRead)
def revoke_key(
    key_id: str,
    user: User = Depends(get_interactive_user),
    session: Session = Depends(get_session, scope="function"),
) -> ApiKeyRead:
    key = service.revoke_api_key(session, user=user, key_id=key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="api key not found")
    return _read(key)
