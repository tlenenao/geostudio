# SPDX-License-Identifier: Apache-2.0
import os
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.export_tokens import ExportTokenError, decode_export_token, is_export_token
from app.db import get_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def is_read_only_mode() -> bool:
    """CORE_READ_ONLY_MODE (mode démo, SP-9) — lu à chaque appel, sans cache,
    même convention que _mock_mode() ci-dessus : les tests basculent le mode
    via monkeypatch sans recréer l'app."""
    return os.environ.get("CORE_READ_ONLY_MODE", "false").lower() == "true"


def is_etl_enabled() -> bool:
    """CORE_ETL_ENABLED (SP-15a) — capacité instance-wide optionnelle, même
    convention que is_read_only_mode : lue à chaque appel, sans cache, pour
    que les tests basculent via monkeypatch sans recréer l'app. Défaut
    false : une instance qui monte en version ne voit rien de nouveau tant
    qu'elle n'a pas explicitement activé la capacité (cf. design SP-15a §3)."""
    return os.environ.get("CORE_ETL_ENABLED", "false").lower() == "true"


def is_export_enabled() -> bool:
    """CORE_EXPORT_ENABLED (SP-17a) — capacité instance-wide optionnelle,
    même convention que is_etl_enabled : lue à chaque appel, sans cache.
    Défaut false : le worker Playwright/export-worker n'est jamais requis
    pour faire tourner le reste de la plateforme."""
    return os.environ.get("CORE_EXPORT_ENABLED", "false").lower() == "true"


def admin_subs() -> set[str]:
    """OIDC subs à promouvoir admin au prochain get_or_create_user (source de
    vérité de CORE_ADMIN_SUBS — utilisée par le chemin REST ci-dessous ET par
    le chemin MCP, app.mcp.tools._resolve_actor)."""
    raw = os.environ.get("CORE_ADMIN_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def analyst_subs() -> set[str]:
    """OIDC subs à promouvoir analyste au prochain get_or_create_user
    (source de vérité de CORE_ANALYST_SUBS) — miroir de admin_subs()."""
    raw = os.environ.get("CORE_ANALYST_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


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
            bootstrap_admin=True,
            bootstrap_analyst=True,
        )

    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        user = session.get(User, claims.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid export token")
        return user

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
        bootstrap_admin=claims["sub"] in admin_subs(),
        bootstrap_analyst=claims["sub"] in analyst_subs(),
    )


def get_current_user_optional(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User | None:
    """Comme get_current_user, mais renvoie None sans header (accès anonyme
    aux collections publiques — URLs OGC stables, spec SP-3 §2)."""
    if not authorization.startswith("Bearer "):
        return None
    return get_current_user(authorization=authorization, session=session)
