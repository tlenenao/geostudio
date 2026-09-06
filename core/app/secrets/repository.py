# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.secrets.crypto import decrypt
from app.secrets.models import ConnectorSecret
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretPayload


def get_secret(session: Session, *, tenant_id: str, secret_id: str) -> ConnectorSecret | None:
    return session.scalar(
        select(ConnectorSecret).where(
            ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.id == secret_id
        )
    )


def get_secret_by_name(session: Session, *, tenant_id: str, name: str) -> ConnectorSecret | None:
    return session.scalar(
        select(ConnectorSecret).where(
            ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.name == name
        )
    )


def create_secret(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    name: str,
    kind: str,
    ciphertext: bytes,
    nonce: bytes,
) -> ConnectorSecret:
    secret = ConnectorSecret(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        name=name,
        kind=kind,
        ciphertext=ciphertext,
        nonce=nonce,
        created_by=created_by,
    )
    session.add(secret)
    session.flush()
    session.refresh(secret)
    return secret


def list_secrets(session: Session, *, tenant_id: str) -> list[ConnectorSecret]:
    return list(
        session.scalars(
            select(ConnectorSecret)
            .where(ConnectorSecret.tenant_id == tenant_id)
            .order_by(ConnectorSecret.name)
        ).all()
    )


def delete_secret(session: Session, secret: ConnectorSecret) -> None:
    session.delete(secret)
    session.flush()


def list_all_secrets(session: Session) -> list[ConnectorSecret]:
    """Cross-tenant, à la différence de toute autre fonction de ce
    module — réservé au script de rotation de la clé maître
    (scripts/rotate_secrets_master_key.py). Ne JAMAIS appeler depuis une
    route HTTP ou un outil MCP : retournerait les secrets de tous les
    tenants à un seul appelant."""
    return list(session.scalars(select(ConnectorSecret)).all())


def get_secret_payload(session: Session, *, tenant_id: str, name: str) -> SecretPayload | None:
    """Déchiffre. Usage interne uniquement (ex. futur runtime SP-15f) —
    jamais appelé depuis un handler de route qui sérialise sa sortie en
    JSON (design §5)."""
    secret = get_secret_by_name(session, tenant_id=tenant_id, name=name)
    if secret is None:
        return None
    return SECRET_PAYLOAD_ADAPTER.validate_python(decrypt(secret.ciphertext, secret.nonce))
