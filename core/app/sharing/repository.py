# SPDX-License-Identifier: Apache-2.0
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare, ShareLink
from app.sharing.models import _now as _sharing_now
from app.users.models import User


def _naive_utc_now() -> datetime:
    # ShareLink.expires_at/revoked_at sont des colonnes DateTime "naïves"
    # (pas timezone=True, cf. app/sharing/models.py) : SQLite ET Postgres
    # renvoient un datetime naïf à la lecture, même quand une valeur
    # aware (_sharing_now(), tz=UTC) a été écrite — comparer un datetime
    # aware à cette valeur naïve lève TypeError. Un utcnow() naïf est la
    # seule forme comparable directement à ce qui revient de la base.
    return datetime.now(UTC).replace(tzinfo=None)


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


def list_groups(
    session: Session,
    *,
    tenant_id: str,
    visible_to: str | None = None,
    q: str | None = None,
    limit: int | None = None,
) -> list[Group]:
    """`visible_to` (id utilisateur) borne aux groupes dont il est membre ou
    créateur ; `q` filtre sur le nom (littéralement) ; `limit` plafonne."""
    stmt = select(Group).where(Group.tenant_id == tenant_id)
    if visible_to is not None:
        member_of = select(GroupMember.group_id).where(GroupMember.user_id == visible_to)
        stmt = stmt.where(or_(Group.created_by == visible_to, Group.id.in_(member_of)))
    if q is not None:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(Group.name.ilike(like, escape="\\"))
    stmt = stmt.order_by(Group.created_at)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


GROUP_SEARCH_LIMIT = 20


def group_names(session: Session, *, tenant_id: str, group_ids: Sequence[str]) -> dict[str, str]:
    """Noms des groupes déjà ciblés par un partage (lecture seule : n'élargit pas l'annuaire)."""
    if not group_ids:
        return {}
    rows = session.execute(
        select(Group.id, Group.name).where(Group.tenant_id == tenant_id, Group.id.in_(group_ids))
    )
    return {gid: name for gid, name in rows}


def directory_groups(
    session: Session, *, tenant_id: str, user_id: str, as_admin: bool, q: str | None
) -> list[Group]:
    """Annuaire de groupes borné (REV-277) — partagé par GET /groups et l'outil
    MCP `list_groups`. Sans `q` : groupes de l'appelant (tout le tenant pour un
    administrateur d'utilisateurs) ; avec `q` : recherche plafonnée sur le tenant."""
    if q is not None:
        return list_groups(session, tenant_id=tenant_id, q=q, limit=GROUP_SEARCH_LIMIT)
    return list_groups(session, tenant_id=tenant_id, visible_to=None if as_admin else user_id)


def get_managed_group(
    session: Session, *, tenant_id: str, group_id: str, caller_id: str, as_admin: bool = False
) -> Group | None:
    """Le groupe si l'appelant peut le gérer (son créateur, ou `as_admin` —
    calculé par la route depuis un privilège d'administration), sinon None
    (traité en 404 : ne révèle ni l'existence ni le tenant d'un groupe)."""
    group = session.get(Group, group_id)
    if group is None or group.tenant_id != tenant_id:
        return None
    if group.created_by != caller_id and not as_admin:
        return None
    return group


def list_members(session: Session, *, group: Group) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group.id, GroupMember.tenant_id == group.tenant_id)
            .order_by(User.username)
        ).all()
    )


def remove_member(session: Session, *, group: Group, user_id: str) -> bool:
    member = session.get(GroupMember, {"group_id": group.id, "user_id": user_id})
    if member is None:
        return False
    session.delete(member)
    session.flush()
    return True


def rename_group(session: Session, *, group: Group, name: str) -> Group:
    group.name = name
    session.flush()
    return group


def delete_group(session: Session, *, group: Group) -> None:
    """Retire le groupe ET tout ce qu'il ouvrait (partages d'items/collections,
    appartenances) — explicite plutôt que via ON DELETE CASCADE, que SQLite
    (tests) n'applique pas."""
    for model in (ItemShare, CollectionShare, GroupMember):
        session.execute(delete(model).where(model.group_id == group.id))
    session.delete(group)
    session.flush()


def add_member(
    session: Session,
    *,
    tenant_id: str,
    group_id: str,
    user_id: str,
    caller_id: str,
    as_admin: bool = False,
) -> bool:
    group = get_managed_group(
        session, tenant_id=tenant_id, group_id=group_id, caller_id=caller_id, as_admin=as_admin
    )
    if group is None:
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


def create_share_link(
    session: Session, *, tenant_id: str, item_id: str, created_by: str, ttl_seconds: int
) -> ShareLink:
    link = ShareLink(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        item_id=item_id,
        created_by=created_by,
        expires_at=_sharing_now() + timedelta(seconds=ttl_seconds),
    )
    session.add(link)
    session.flush()
    session.refresh(link)
    return link


def list_share_links(session: Session, *, tenant_id: str, item_id: str) -> list[ShareLink]:
    return list(
        session.scalars(
            select(ShareLink)
            .where(ShareLink.tenant_id == tenant_id, ShareLink.item_id == item_id)
            .order_by(ShareLink.created_at)
        ).all()
    )


def usernames_by_id(session: Session, *, user_ids: Sequence[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = session.execute(select(User.id, User.username).where(User.id.in_(list(user_ids))))
    return {uid: name for uid, name in rows}


def revoke_share_link(session: Session, *, tenant_id: str, item_id: str, link_id: str) -> bool:
    link = session.get(ShareLink, link_id)
    # c01-006 : le lien doit appartenir à l'item dont l'appelant a vérifié le droit.
    if link is None or link.tenant_id != tenant_id or link.item_id != item_id:
        return False
    if link.revoked_at is None:
        link.revoked_at = _sharing_now()
        session.flush()
    return True


def get_active_share_link(session: Session, *, tenant_id: str, link_id: str) -> ShareLink | None:
    """None si absent, révoqué, ou expiré (double vérification : la ligne
    ET le TTL du jeton, cf. spec §6.1 — la ligne prime si elle diverge du
    TTL du jeton, ex. un jeton pas encore expiré mais révoqué)."""
    link = session.get(ShareLink, link_id)
    if link is None or link.tenant_id != tenant_id:
        return None
    if link.revoked_at is not None:
        return None
    if link.expires_at <= _naive_utc_now():
        return None
    return link
