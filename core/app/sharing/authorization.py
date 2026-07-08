from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.sharing.repository import has_group_role

Action = Literal["read", "write", "delete", "share"]


@dataclass(frozen=True)
class ItemAccessFacts:
    """Everything `can()` needs about one item, without importing
    `app.items.models.Item` (app.sharing sits below app.items in the
    layering — see plan Architecture). Callers build this from an Item row
    they already fetched."""

    id: str
    tenant_id: str
    owner_id: str
    is_public: bool
    is_published: bool


def can(session: Session, *, user_id: str, action: Action, item: ItemAccessFacts) -> bool:
    if item.owner_id == user_id:
        return True
    if action == "read":
        if item.is_public or item.is_published:
            return True
        return has_group_role(
            session, tenant_id=item.tenant_id, item_id=item.id, user_id=user_id,
            roles={"viewer", "editor"},
        )
    if action in ("write", "delete", "share"):
        return has_group_role(
            session, tenant_id=item.tenant_id, item_id=item.id, user_id=user_id,
            roles={"editor"},
        )
    return False
