from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.sharing.authorization import AccessFacts
from app.sharing.models import CollectionShare, Group, GroupMember


def get_access_facts(col: Collection) -> AccessFacts:
    return AccessFacts(
        id=col.id, tenant_id=col.tenant_id, owner_id=col.owner_id,
        is_public=col.is_public, is_published=False,
    )


def get_collection(session: Session, *, tenant_id: str, collection_id: str) -> Collection | None:
    return session.scalar(select(Collection).where(
        Collection.tenant_id == tenant_id, Collection.id == collection_id))


def create_collection(session: Session, *, tenant_id: str, owner_id: str, table_name: str,
                      title: str, description: str, is_public: bool,
                      pk_column: str, geometry_column: str | None,
                      geometry_type: str | None, srid: int | None) -> Collection:
    col = Collection(
        id=table_name, tenant_id=tenant_id, owner_id=owner_id, table_name=table_name,
        title=title, description=description, is_public=is_public, pk_column=pk_column,
        geometry_column=geometry_column, geometry_type=geometry_type, srid=srid,
    )
    session.add(col)
    session.flush()
    return col


def list_visible_collections(
    session: Session, *, tenant_id: str, user_id: str | None, is_admin: bool
) -> list[Collection]:
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not is_admin:
        if user_id is None:
            stmt = stmt.where(Collection.is_public.is_(True))
        else:
            shared_ids = (
                select(CollectionShare.collection_id)
                .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
                .where(GroupMember.user_id == user_id,
                       CollectionShare.tenant_id == tenant_id)
            )
            stmt = stmt.where(
                Collection.is_public.is_(True)
                | (Collection.owner_id == user_id)
                | Collection.id.in_(shared_ids)
            )
    return list(session.scalars(stmt.order_by(Collection.title)).all())


def delete_collection(session: Session, col: Collection) -> None:
    session.delete(col)
    session.flush()


def get_collection_sharing(
    session: Session, *, tenant_id: str, collection_id: str
) -> list[CollectionShare]:
    return list(session.scalars(select(CollectionShare).where(
        CollectionShare.tenant_id == tenant_id,
        CollectionShare.collection_id == collection_id,
    )).all())


def set_collection_sharing(
    session: Session, *, tenant_id: str, collection_id: str,
    groups: list[tuple[str, str]],  # [(group_id, role)]
) -> bool:
    """Replace all group shares for one collection. Returns False (no changes
    made) if any group_id doesn't belong to tenant_id — the caller must treat
    this as a 404 (never leak cross-tenant group existence). Same contract as
    app/sharing/repository.py::replace_shares for items."""
    group_ids = [group_id for group_id, _role in groups]
    if group_ids:
        matching = session.scalar(
            select(func.count())
            .select_from(Group)
            .where(Group.tenant_id == tenant_id, Group.id.in_(group_ids))
        )
        if matching != len(set(group_ids)):
            return False

    session.execute(delete(CollectionShare).where(
        CollectionShare.tenant_id == tenant_id,
        CollectionShare.collection_id == collection_id,
    ))
    for group_id, role in groups:
        session.add(CollectionShare(collection_id=collection_id, group_id=group_id,
                                    tenant_id=tenant_id, role=role))
    session.flush()
    return True
