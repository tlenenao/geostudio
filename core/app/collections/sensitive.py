# SPDX-License-Identifier: Apache-2.0
"""Verdict de lecture des champs sensibles (GAP-22) — point unique.

Décision 2026-10-11 (REV-276/j07-016) : lisent en clair `data.view_sensitive`,
`admin.collections.manage` et le propriétaire de la collection ; tout autre
lecteur est masqué. Tous les chemins de lecture (REST, tuiles, STAC, exports,
lac DuckDB, MCP, alertes, pipelines) passent par ici."""

from sqlalchemy.orm import Session

from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.users.models import User


def has_sensitive_privilege(session: Session, user: User | None) -> bool:
    """Volet « privilège » du verdict (indépendant de la collection)."""
    return user is not None and (
        has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
        or has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )


def is_owner(user: User | None, col) -> bool:
    return user is not None and col.owner_id == user.id


def may_read_sensitive(session: Session, user: User | None, col) -> bool:
    return is_owner(user, col) or has_sensitive_privilege(session, user)


def unmask_for_owner(masked: bool, user: User | None, col) -> bool:
    """Affine un verdict utilisateur (`get_masked_for_user`) pour une collection."""
    return masked and not is_owner(user, col)


def masked_fields_for(session: Session, user: User | None, col) -> frozenset[str]:
    return (
        frozenset() if may_read_sensitive(session, user, col) else frozenset(col.sensitive_fields)
    )
