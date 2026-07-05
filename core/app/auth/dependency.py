import os
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get(
        "CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"
    )
    return jwt.PyJWKClient(jwks_url, lifespan=600)


def get_current_user(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User:
    tenant = get_or_create_default_tenant(session)

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")

    if _mock_mode():
        return get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=os.environ["CORE_OIDC_AUDIENCE"],
            issuer=os.environ["CORE_OIDC_ISSUER"],
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(status_code=503, detail="identity provider unreachable") from exc
    except jwt.PyJWKClientError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        email=claims.get("email"),
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
    )
