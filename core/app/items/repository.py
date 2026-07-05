import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.schemas import ItemPage, ItemRead
from app.users.models import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_read(item: Item, owner_username: str) -> ItemRead:
    # configId is always None: app.items must never import app.configs (see
    # plan Architecture — items sits below configs in the layering), and the
    # shell's own Item.configId is already hardcoded to null everywhere today
    # (itemClient.ts's toItem()), so this isn't a behavior regression for any
    # current consumer. Real wiring, if ever needed, belongs in app.configs.
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
    )


def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str
) -> Item:
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def get_item(session: Session, *, tenant_id: str, item_id: str) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).first()
    if row is None:
        return None
    item, owner_username = row
    return _to_read(item, owner_username)


def list_items(
    session: Session,
    *,
    tenant_id: str,
    current_user_id: str,
    q: str | None,
    resource_type: str | None,
    scope: str,
    page: int,
    page_size: int,
) -> ItemPage:
    if scope == "shared":
        return ItemPage(items=[], total=0, page=page, pageSize=page_size)

    query = select(Item, User.username).join(User, User.id == Item.owner_id).where(Item.tenant_id == tenant_id)
    if resource_type:
        query = query.where(Item.resource_type == resource_type)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))
    if scope == "mine":
        query = query.where(Item.owner_id == current_user_id)
    elif scope == "public":
        query = query.where(Item.is_published.is_(True))
    # scope == "all": no extra filter (real visibility filtering arrives in SP-1c)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Item.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_read(item, owner_username) for item, owner_username in rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)


def update_item(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    title: str | None,
    abstract: str | None,
    keywords: list[str] | None,
    is_published: bool | None,
) -> ItemRead | None:
    item = session.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return None
    if title is not None:
        item.title = title
    if abstract is not None:
        item.abstract = abstract
    if keywords is not None:
        item.keywords = keywords
    if is_published is not None:
        item.is_published = is_published
    session.commit()
    session.refresh(item)
    owner_username = session.scalar(select(User.username).where(User.id == item.owner_id)) or ""
    return _to_read(item, owner_username)
