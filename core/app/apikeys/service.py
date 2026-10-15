# SPDX-License-Identifier: Apache-2.0
"""Clés d'API de service (ARC-06, ADR 0016).

Une clé résout vers son CRÉATEUR (`User`) : rôle et partages sont ceux du
créateur à chaque requête, donc la clé ne dépasse jamais ses privilèges.
Datetimes naïfs UTC en base (convention du dépôt)."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.apikeys.models import ApiKey
from app.audit.writer import write_audit
from app.users.models import User

TOKEN_PREFIX = "gsk_"
# Jeton = "gsk_" + 12 hex (préfixe public, 16 car.) + "_" + secret urlsafe 256 bits.
_PREFIX_LEN = len(TOKEN_PREFIX) + 12
MAX_LIFETIME_DAYS = 365
# Trace d'usage au plus 1 fois/min/clé : borne l'écriture sur les lectures chaudes.
USE_AUDIT_INTERVAL = timedelta(seconds=60)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def is_api_key(token: str) -> bool:
    return token.startswith(TOKEN_PREFIX)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_api_key(
    session: Session, *, user: User, name: str, expires_in_days: int
) -> tuple[ApiKey, str]:
    """Renvoie (ligne, jeton en clair) ; le jeton n'existe nulle part ailleurs."""
    if not 1 <= expires_in_days <= MAX_LIFETIME_DAYS:
        raise ValueError(f"expires_in_days must be between 1 and {MAX_LIFETIME_DAYS}")
    prefix = TOKEN_PREFIX + secrets.token_hex(6)
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    key = ApiKey(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        created_by=user.id,
        name=name,
        key_prefix=prefix,
        key_hash=_hash(token),
        expires_at=_utcnow() + timedelta(days=expires_in_days),
    )
    session.add(key)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="api_key.create",
        object_type="api_key",
        object_id=key.id,
        payload={"prefix": prefix, "name": name, "expiresAt": key.expires_at.isoformat()},
    )
    return key, token


def list_api_keys(session: Session, *, user: User, created_by: str | None = None) -> list[ApiKey]:
    """Clés de `user` ; `created_by` (appel admin, REV-366) vise les clés d'un autre compte
    du même tenant — l'autorisation (`admin.users.manage`) est celle de la route."""
    return list(
        session.scalars(
            select(ApiKey)
            .where(ApiKey.tenant_id == user.tenant_id, ApiKey.created_by == (created_by or user.id))
            .order_by(ApiKey.created_at.desc())
        )
    )


def revoke_api_key(
    session: Session, *, user: User, key_id: str, any_owner: bool = False
) -> ApiKey | None:
    """`any_owner=True` : révocation admin (REV-366) d'une clé d'un autre compte du tenant."""
    query = select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == user.tenant_id)
    if not any_owner:
        query = query.where(ApiKey.created_by == user.id)
    key = session.scalars(query).first()
    if key is None:
        return None
    if key.revoked_at is None:
        key.revoked_at = _utcnow()
        session.flush()
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="api_key.revoke",
            object_type="api_key",
            object_id=key.id,
            payload={"prefix": key.key_prefix, "createdBy": key.created_by},
        )
    return key


def revoke_all_for_user(session: Session, *, tenant_id: str, user_id: str) -> None:
    """RGPD (anonymisation) : plus aucune clé ne doit survivre au compte."""
    session.execute(
        update(ApiKey)
        .where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.created_by == user_id,
            ApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )


def authenticate(session: Session, *, token: str, tenant_id: str) -> User | None:
    """Le créateur de la clé si elle est valide, sinon None (cause jamais
    distinguée : pas d'oracle). Recherche par préfixe public, puis condensats
    comparés à temps constant."""
    if len(token) <= _PREFIX_LEN + 1 or token[_PREFIX_LEN] != "_":
        return None
    key = session.scalars(select(ApiKey).where(ApiKey.key_prefix == token[:_PREFIX_LEN])).first()
    # Comparaison faite même si la clé est introuvable (condensat factice) :
    # le temps de réponse ne révèle pas l'existence du préfixe.
    expected = key.key_hash if key is not None else "0" * 64
    if not hmac.compare_digest(_hash(token), expected) or key is None:
        return None
    now = _utcnow()
    if key.tenant_id != tenant_id or key.revoked_at is not None or key.expires_at <= now:
        return None
    user = session.get(User, key.created_by)
    if user is None or user.erased_at is not None:
        return None
    if key.last_used_at is None or now - key.last_used_at >= USE_AUDIT_INTERVAL:
        key.last_used_at = now
        session.flush()
        write_audit(
            session,
            tenant_id=key.tenant_id,
            actor_id=user.id,
            actor_kind="api_key",
            action="api_key.use",
            object_type="api_key",
            object_id=key.id,
            payload={"prefix": key.key_prefix},
        )
    return user
