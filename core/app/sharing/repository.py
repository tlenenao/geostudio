# SPDX-License-Identifier: Apache-2.0
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
from app.users.models import User


def roles_for_items(
    session: Session, *, tenant_id: str, user_id: str, item_ids: Sequence[str]
) -> dict[str, frozenset[str]]:
    """Les rôles de groupe de `user_id` sur chacun des `item_ids`, en **une**
    requête.

    Élimine le pattern N+1 d'une requête par item et par jeu de rôles : la
    sérialisation d'une page de catalogue a besoin des rôles de douze items
    à la fois, et le faire ligne par ligne était le N+1 que
    `tests/test_items_no_nplus1.py` interdit désormais.

    Une clé absente du résultat signifie « aucun rôle » — les appelants
    utilisent `.get(id, frozenset())`.
    """
    if not item_ids:
        return {}
    rows = session.execute(
        select(ItemShare.item_id, ItemShare.role)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id.in_(list(item_ids)),
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
    ).all()
    out: dict[str, set[str]] = {}
    for item_id, role in rows:
        out.setdefault(item_id, set()).add(role)
    return {k: frozenset(v) for k, v in out.items()}


def roles_for_collections(
    session: Session, *, tenant_id: str, user_id: str, collection_ids: Sequence[str]
) -> dict[str, frozenset[str]]:
    """Pendant de `roles_for_items` pour les collections. Même contrat."""
    if not collection_ids:
        return {}
    rows = session.execute(
        select(CollectionShare.collection_id, CollectionShare.role)
        .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
        .where(
            CollectionShare.collection_id.in_(list(collection_ids)),
            CollectionShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
    ).all()
    out: dict[str, set[str]] = {}
    for collection_id, role in rows:
        out.setdefault(collection_id, set()).add(role)
    return {k: frozenset(v) for k, v in out.items()}


def create_group(session: Session, *, tenant_id: str, name: str, created_by: str) -> Group:
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant_id, name=name, created_by=created_by)
    session.add(group)
    session.flush()
    session.refresh(group)
    return group


def list_groups(session: Session, *, tenant_id: str) -> list[Group]:
    return list(
        session.scalars(
            select(Group).where(Group.tenant_id == tenant_id).order_by(Group.created_at)
        ).all()
    )


def add_member(
    session: Session, *, tenant_id: str, group_id: str, user_id: str, caller_id: str
) -> bool:
    group = session.get(Group, group_id)
    if group is None or group.tenant_id != tenant_id:
        return False
    if group.created_by != caller_id:
        return False
    user_tenant = session.scalar(select(User.tenant_id).where(User.id == user_id))
    if user_tenant != tenant_id:
        return False
    existing = session.get(GroupMember, {"group_id": group_id, "user_id": user_id})
    if existing is None:
        session.add(GroupMember(group_id=group_id, user_id=user_id, tenant_id=tenant_id))
        session.flush()
    return True


def list_shares(session: Session, *, item_id: str) -> list[ItemShare]:
    return list(session.scalars(select(ItemShare).where(ItemShare.item_id == item_id)).all())


def replace_shares(
    session: Session, *, tenant_id: str, item_id: str, shares: list[tuple[str, str]]
) -> bool:
    """Replace all group shares for one item. Returns False (no changes made)
    if any group_id doesn't belong to tenant_id — the caller must treat this
    as a 404 (never leak cross-tenant group existence)."""
    group_ids = [group_id for group_id, _role in shares]
    if group_ids:
        matching = session.scalar(
            select(func.count())
            .select_from(Group)
            .where(Group.tenant_id == tenant_id, Group.id.in_(group_ids))
        )
        if matching != len(set(group_ids)):
            return False

    session.execute(delete(ItemShare).where(ItemShare.item_id == item_id))
    for group_id, role in shares:
        session.add(ItemShare(item_id=item_id, group_id=group_id, tenant_id=tenant_id, role=role))
    session.flush()
    return True
