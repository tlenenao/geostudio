# SPDX-License-Identifier: Apache-2.0
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.models import Config, ConfigRevision
from app.items.models import Item
from app.items.repository import get_access_facts_by_ids
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.secrets.crypto import decrypt
from app.secrets.models import ConnectorSecret
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretPayload
from app.sharing.authorization import can
from app.users.models import User


def can_use_secret(session: Session, user: User, secret: ConnectorSecret) -> bool:
    """ACL du coffre (P16.01) : propriétaire du secret, ou privilège
    admin.secrets.manage. automation.secrets.manage seul ne donne accès
    qu'à ses propres secrets."""
    return secret.created_by == user.id or has_privilege(
        session, user, Privilege.ADMIN_SECRETS_MANAGE.value
    )


def get_secret(session: Session, *, tenant_id: str, secret_id: str) -> ConnectorSecret | None:
    """Sans ACL — les routes appliquent can_use_secret."""
    return session.scalar(
        select(ConnectorSecret).where(
            ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.id == secret_id
        )
    )


def get_visible_secret(
    session: Session, *, tenant_id: str, secret_id: str, user: User
) -> ConnectorSecret | None:
    """get_secret + ACL : un secret d'autrui est indistinguable d'un absent."""
    secret = get_secret(session, tenant_id=tenant_id, secret_id=secret_id)
    return secret if secret is not None and can_use_secret(session, user, secret) else None


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


def list_secrets(session: Session, *, tenant_id: str, user: User) -> list[ConnectorSecret]:
    """Seulement les secrets que `user` peut utiliser (P16.01)."""
    rows = session.scalars(
        select(ConnectorSecret)
        .where(ConnectorSecret.tenant_id == tenant_id)
        .order_by(ConnectorSecret.name)
    ).all()
    return [s for s in rows if can_use_secret(session, user, s)]


def _references(node: Any, name: str) -> bool:
    if isinstance(node, dict):
        return any(
            (k in {"secretName", "smtpSecretName", "signingSecretName"} and v == name)
            or _references(v, name)
            for k, v in node.items()
        )
    if isinstance(node, list):
        return any(_references(v, name) for v in node)
    return False


def find_usages(session: Session, *, tenant_id: str, name: str) -> list[dict[str, str]]:
    """Items (pipelines, alertes, rapports…) dont la config courante cite
    ce secret par son nom (P16.05)."""
    rows = session.execute(
        select(Item.id, Item.title, ConfigRevision.data)
        .join(Config, Config.item_id == Item.id)
        .join(
            ConfigRevision,
            (ConfigRevision.config_id == Config.id)
            & (ConfigRevision.version == Config.current_version),
        )
        .where(Config.tenant_id == tenant_id)
    ).all()
    return [{"itemId": i, "title": t} for i, t, data in rows if _references(data, name)]


class SecretInUseError(Exception):
    pass


def delete_secret_unless_used(session: Session, secret: ConnectorSecret, *, user: User) -> None:
    """Refuse (SecretInUseError) si une config cite encore le secret (P16.05).
    REV-273c : le message ne liste que les objets que `user` peut lire
    (`can(read)`) ; les autres sont comptés, jamais nommés."""
    usages = find_usages(session, tenant_id=secret.tenant_id, name=secret.name)
    if not usages:
        delete_secret(session, secret)
        return
    facts = get_access_facts_by_ids(
        session, tenant_id=secret.tenant_id, item_ids=[u["itemId"] for u in usages]
    )
    visible = [
        u["title"]
        for u in usages
        if (f := facts.get(u["itemId"])) is not None
        and can(session, user_id=user.id, action="read", item=f)
    ]
    hidden = len(usages) - len(visible)
    parts: list[str] = []
    if visible:
        parts.append(", ".join(visible))
    if hidden:
        s = "s" if hidden > 1 else ""
        parts.append(f"{hidden} autre{s} objet{s} non visible{s}")
    raise SecretInUseError("secret encore utilisé par : " + " et ".join(parts))


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


def get_secret_payload(
    session: Session, *, tenant_id: str, name: str, user: User
) -> SecretPayload | None:
    """Déchiffre. Usage interne uniquement (ex. futur runtime SP-15f) —
    jamais appelé depuis un handler de route qui sérialise sa sortie en
    JSON (design §5). `user` = l'acteur qui utilise le secret (P16.01) :
    un secret qu'il ne peut pas utiliser est indistinguable d'un secret
    absent (None)."""
    secret = get_secret_by_name(session, tenant_id=tenant_id, name=name)
    if secret is None or not can_use_secret(session, user, secret):
        return None
    return SECRET_PAYLOAD_ADAPTER.validate_python(decrypt(secret.ciphertext, secret.nonce))
