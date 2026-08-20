# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.sharing.repository import has_collection_group_role, has_group_role

Action = Literal["read", "write", "delete", "share"]
ObjectKind = Literal["item", "collection"]


@dataclass(frozen=True)
class AccessFacts:
    """Everything `can()` needs about one object, without importing the model
    (app.sharing sits below app.items and app.collections in the layering).
    Callers build this from a row they already fetched."""

    id: str
    tenant_id: str
    owner_id: str
    is_public: bool
    is_published: bool


# Rétro-compatibilité : les routes items/configs existantes importent ce nom.
ItemAccessFacts = AccessFacts


def can(
    session: Session,
    *,
    user_id: str,
    action: Action,
    item: AccessFacts,
    kind: ObjectKind = "item",
    actor_is_admin: bool = False,
) -> bool:
    # Le rôle admin ne court-circuite QUE les collections (spec SP-3 §2) :
    # la sémantique de partage des items (SP-1, testée) ne bouge pas.
    if kind == "collection" and actor_is_admin:
        return True
    if item.owner_id == user_id:
        return True

    def role_check(roles: set[str]) -> bool:
        if kind == "item":
            return has_group_role(
                session,
                tenant_id=item.tenant_id,
                item_id=item.id,
                user_id=user_id,
                roles=roles,
            )
        return has_collection_group_role(
            session,
            tenant_id=item.tenant_id,
            collection_id=item.id,
            user_id=user_id,
            roles=roles,
        )

    if action == "read":
        if item.is_public or item.is_published:
            return True
        return role_check({"viewer", "editor"})
    if action in ("write", "delete", "share"):
        return role_check({"editor"})
    return False
