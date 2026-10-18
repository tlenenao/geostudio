# SPDX-License-Identifier: Apache-2.0
"""Droit d'accès / portabilité (RGPD Art. 15/20, AUD-120) : dossier JSON d'un utilisateur.

Contenu : profil, groupes, items et collections possédés (métadonnées, pas les données
métier des collections), clés d'API (métadonnées, jamais le secret), notifications,
lignes d'audit dont il est l'acteur, journal d'entité (modifications de fiches). Chaque
liste est plafonnée à `MAX_PER_SECTION` (signalé par `truncated`)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apikeys.models import ApiKey
from app.audit.models import AuditLog
from app.collections.models import Collection
from app.history.models import EntityHistory
from app.items.models import Item
from app.notifications.models import Notification
from app.saved_queries.models import SavedQuery
from app.sharing.models import Group, GroupMember
from app.users.models import User

MAX_PER_SECTION = 10_000


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _section(session: Session, stmt, to_dict, truncated: list[str], name: str) -> list[dict]:
    rows = session.execute(stmt.limit(MAX_PER_SECTION + 1)).all()
    if len(rows) > MAX_PER_SECTION:
        truncated.append(name)
        rows = rows[:MAX_PER_SECTION]
    return [to_dict(*r) for r in rows]


def export_user_data(session: Session, *, tenant_id: str, user_id: str) -> dict:
    user = session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise LookupError(f"user '{user_id}' not found in tenant '{tenant_id}'")
    truncated: list[str] = []
    return {
        "generatedAt": _iso(datetime.now(UTC)),
        "profile": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "firstName": user.first_name,
            "lastName": user.last_name,
            "roleId": user.role_id,
            "createdAt": _iso(user.created_at),
            "erasedAt": _iso(user.erased_at),
        },
        "groups": _section(
            session,
            select(Group.id, Group.name)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id, Group.tenant_id == tenant_id),
            lambda gid, name: {"id": gid, "name": name},
            truncated,
            "groups",
        ),
        "items": _section(
            session,
            select(Item.id, Item.resource_type, Item.title, Item.created_at)
            .where(Item.owner_id == user_id, Item.tenant_id == tenant_id)
            .order_by(Item.created_at),
            lambda i, t, title, c: {"id": i, "type": t, "title": title, "createdAt": _iso(c)},
            truncated,
            "items",
        ),
        "collections": _section(
            session,
            select(Collection.id, Collection.title)
            .where(Collection.owner_id == user_id, Collection.tenant_id == tenant_id)
            .order_by(Collection.id),
            lambda i, title: {"id": i, "title": title},
            truncated,
            "collections",
        ),
        "apiKeys": _section(
            session,
            select(ApiKey.id, ApiKey.name, ApiKey.created_at, ApiKey.expires_at, ApiKey.revoked_at)
            .where(ApiKey.created_by == user_id, ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at),
            lambda i, n, c, e, r: {
                "id": i,
                "name": n,
                "createdAt": _iso(c),
                "expiresAt": _iso(e),
                "revokedAt": _iso(r),
            },
            truncated,
            "apiKeys",
        ),
        "notifications": _section(
            session,
            select(
                Notification.id, Notification.kind, Notification.item_title, Notification.created_at
            )
            .where(Notification.recipient_user_id == user_id, Notification.tenant_id == tenant_id)
            .order_by(Notification.created_at),
            lambda i, k, t, c: {"id": i, "kind": k, "itemTitle": t, "createdAt": _iso(c)},
            truncated,
            "notifications",
        ),
        "savedQueries": _section(  # AUD-062 : texte SQL écrit par la personne
            session,
            select(SavedQuery.id, SavedQuery.name, SavedQuery.sql, SavedQuery.created_at)
            .where(SavedQuery.owner_id == user_id, SavedQuery.tenant_id == tenant_id)
            .order_by(SavedQuery.created_at),
            lambda i, n, s, c: {"id": i, "name": n, "sql": s, "createdAt": _iso(c)},
            truncated,
            "savedQueries",
        ),
        "auditLog": _section(
            session,
            select(
                AuditLog.id,
                AuditLog.action,
                AuditLog.object_type,
                AuditLog.object_id,
                AuditLog.payload,
                AuditLog.created_at,
            )
            .where(AuditLog.actor_id == user_id, AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.id),
            lambda i, a, ot, oi, p, c: {
                "id": i,
                "action": a,
                "objectType": ot,
                "objectId": oi,
                "payload": p,
                "createdAt": _iso(c),
            },
            truncated,
            "auditLog",
        ),
        "entityHistory": _section(
            session,
            select(
                EntityHistory.collection_id,
                EntityHistory.fid,
                EntityHistory.op,
                EntityHistory.created_at,
            )
            .where(EntityHistory.actor_id == user_id, EntityHistory.tenant_id == tenant_id)
            .order_by(EntityHistory.id),
            lambda col, fid, op, c: {
                "collectionId": col,
                "fid": fid,
                "op": op,
                "createdAt": _iso(c),
            },
            truncated,
            "entityHistory",
        ),
        "truncated": truncated,
    }
