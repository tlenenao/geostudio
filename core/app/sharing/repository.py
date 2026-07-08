import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.sharing.models import Group, GroupMember, ItemShare
from app.users.models import User


def has_group_role(
    session: Session, *, tenant_id: str, item_id: str, user_id: str, roles: set[str]
) -> bool:
    stmt = (
        select(ItemShare.role)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id == item_id,
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
            ItemShare.role.in_(roles),
        )
    )
    return session.scalar(stmt) is not None


def create_group(session: Session, *, tenant_id: str, name: str) -> Group:
    group = Group(id=uuid.uuid4().hex, tenant_id=tenant_id, name=name)
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


def add_member(session: Session, *, tenant_id: str, group_id: str, user_id: str) -> bool:
    group = session.get(Group, group_id)
    if group is None or group.tenant_id != tenant_id:
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
    return list(
        session.scalars(select(ItemShare).where(ItemShare.item_id == item_id)).all()
    )


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
