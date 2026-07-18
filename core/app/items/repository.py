# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from datetime import datetime, timezone

import procrastinate
from opentelemetry import metrics
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.schemas import ItemPage, ItemRead
from app.items.slug import InvalidSlugError, SlugCollisionError, is_valid_slug, slugify
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids
from app.sharing.authorization import ItemAccessFacts
from app.sharing.models import GroupMember, ItemShare
from app.users.models import User

logger = logging.getLogger(__name__)

_RRF_CANDIDATE_LIMIT = 200

_meter = metrics.get_meter(__name__)
_items_created_counter = _meter.create_counter(
    "geostudio.items.created", unit="1", description="Items created via REST or MCP",
)
_items_published_counter = _meter.create_counter(
    "geostudio.configs.published", unit="1", description="Items patched with isPublished=True",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enqueue_embedding(item_id: str, tenant_id: str) -> None:
    # Best-effort : le calcul d'embedding est déjà fail-open (app.items.jobs.
    # embed_item_task ne bloque jamais l'écriture sur un fournisseur lent ou
    # indisponible, spec §Pipeline d'embedding). L'ENQUEUE elle-même doit
    # suivre le même principe — sans quoi une file procrastinate
    # injoignable transformerait un simple "l'item restera cherchable par
    # trigram seul" en 500 sur toute création/modification d'item. Import
    # local (pas en tête de fichier) : évite un cycle d'import — app.items.
    # jobs importe app.items.models, importé transitivement très tôt par
    # app.db.core_table_names().
    from app.items.jobs import embed_item_task
    try:
        embed_item_task.defer(item_id=item_id, tenant_id=tenant_id)
    except procrastinate.exceptions.ProcrastinateException:
        logger.exception(
            "échec de l'enqueue du job d'embedding pour l'item %s (l'écriture "
            "n'est pas affectée ; l'embedding restera NULL jusqu'au prochain write)",
            item_id,
        )


def _to_read(item: Item, owner_username: str) -> ItemRead:
    # configId is always None: app.items must never import app.configs (see
    # plan Architecture — items sits below configs in the layering), and the
    # shell's own Item.configId is already hardcoded to null everywhere today
    # (itemClient.ts's toItem()), so this isn't a behavior regression for any
    # current consumer. Real wiring, if ever needed, belongs in app.configs.
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        slug=item.slug,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
    )


def slug_exists(
    session: Session, *, tenant_id: str, slug: str, exclude_item_id: str | None = None
) -> bool:
    stmt = select(Item.id).where(Item.tenant_id == tenant_id, Item.slug == slug)
    if exclude_item_id is not None:
        stmt = stmt.where(Item.id != exclude_item_id)
    return session.execute(stmt).first() is not None


def ensure_unique_slug(session: Session, *, tenant_id: str, base: str) -> str:
    if not slug_exists(session, tenant_id=tenant_id, slug=base):
        return base
    n = 2
    while slug_exists(session, tenant_id=tenant_id, slug=f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def _resolve_site_slug(
    session: Session, *, tenant_id: str, title: str, slug: str | None
) -> str:
    if slug is None:
        return ensure_unique_slug(session, tenant_id=tenant_id, base=slugify(title))
    if not is_valid_slug(slug):
        raise InvalidSlugError(f"slug invalide: {slug!r}")
    if slug_exists(session, tenant_id=tenant_id, slug=slug):
        raise SlugCollisionError(f"slug déjà utilisé: {slug!r}")
    return slug


def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str,
    slug: str | None = None,
) -> Item:
    resolved_slug = None
    if resource_type == "site":
        resolved_slug = _resolve_site_slug(session, tenant_id=tenant_id, title=title, slug=slug)
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title, slug=resolved_slug,
    )
    session.add(item)
    session.flush()
    session.refresh(item)
    _enqueue_embedding(item.id, tenant_id)
    _items_created_counter.add(1)
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


def get_access_facts(session: Session, *, tenant_id: str, item_id: str) -> ItemAccessFacts | None:
    row = session.execute(
        select(Item.id, Item.tenant_id, Item.owner_id, Item.is_public, Item.is_published)
        .where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).first()
    if row is None:
        return None
    return ItemAccessFacts(
        id=row.id, tenant_id=row.tenant_id, owner_id=row.owner_id,
        is_public=row.is_public, is_published=row.is_published,
    )


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
    query = select(Item, User.username).join(User, User.id == Item.owner_id).where(Item.tenant_id == tenant_id)
    if resource_type:
        query = query.where(Item.resource_type == resource_type)

    shared_exists = (
        select(ItemShare.item_id)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id == Item.id,
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == current_user_id,
            GroupMember.tenant_id == tenant_id,
        )
        .exists()
    )
    if scope == "mine":
        query = query.where(Item.owner_id == current_user_id)
    elif scope == "public":
        query = query.where(Item.is_published.is_(True))
    elif scope == "shared":
        query = query.where(Item.owner_id != current_user_id, shared_exists)
    elif scope == "all":
        query = query.where(
            or_(
                Item.owner_id == current_user_id,
                Item.is_public.is_(True),
                Item.is_published.is_(True),
                shared_exists,
            )
        )
    # À ce stade, `query` ne contient que des lignes visibles par
    # current_user_id — c'est la base sur laquelle la recherche (hybride ou
    # ILIKE) s'exécute ensuite (spec §Recherche hybride + permissions : le
    # filtre can()/scope passe TOUJOURS avant le scoring).

    if q and session.get_bind().dialect.name == "postgresql":
        provider = get_embedding_provider()
        candidate_ids = hybrid_search_ids(
            session, base_stmt=query, id_column=Item.id,
            text_columns=[Item.title, Item.abstract], embedding_column=Item.embedding,
            query_text=q, query_vector=provider.embed(q), limit=_RRF_CANDIDATE_LIMIT,
        )
        total = len(candidate_ids)
        page_ids = candidate_ids[(page - 1) * page_size: (page - 1) * page_size + page_size]
        rows = session.execute(
            select(Item, User.username).join(User, User.id == Item.owner_id)
            .where(Item.id.in_(page_ids))
        ).all()
        by_id = {item.id: (item, owner_username) for item, owner_username in rows}
        items = [_to_read(*by_id[i]) for i in page_ids if i in by_id]
        return ItemPage(items=items, total=total, page=page, pageSize=page_size)

    if q:
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Item.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_read(item, owner_username) for item, owner_username in rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)


def set_thumbnail_key(session: Session, *, tenant_id: str, item_id: str, thumbnail_key: str) -> None:
    item = session.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return
    item.thumbnail_key = thumbnail_key
    session.flush()


def get_thumbnail_key(session: Session, *, tenant_id: str, item_id: str) -> str | None:
    return session.scalar(
        select(Item.thumbnail_key).where(Item.id == item_id, Item.tenant_id == tenant_id)
    )


def update_item(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    title: str | None,
    abstract: str | None,
    keywords: list[str] | None,
    is_published: bool | None,
    slug: str | None = None,
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
    if is_published is True:
        _items_published_counter.add(1)
    if slug is not None:
        if not is_valid_slug(slug):
            raise InvalidSlugError(f"slug invalide: {slug!r}")
        if slug_exists(session, tenant_id=tenant_id, slug=slug, exclude_item_id=item_id):
            raise SlugCollisionError(f"slug déjà utilisé: {slug!r}")
        item.slug = slug
    session.flush()
    session.refresh(item)
    owner_username = session.scalar(select(User.username).where(User.id == item.owner_id)) or ""
    _enqueue_embedding(item.id, tenant_id)
    return _to_read(item, owner_username)


def get_published_item(session: Session, *, item_id: str) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.id == item_id, Item.is_published.is_(True))
    ).first()
    if row is None:
        return None
    item, owner_username = row
    return _to_read(item, owner_username)


def set_is_public(session: Session, *, tenant_id: str, item_id: str, is_public: bool) -> None:
    item = session.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return
    item.is_public = is_public
    session.flush()
