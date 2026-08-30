# SPDX-License-Identifier: Apache-2.0
import logging

import procrastinate
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.collections.schemas import CollectionPermissions
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids
from app.sharing.authorization import AccessFacts, Action, decide
from app.sharing.models import CollectionShare, Group, GroupMember
from app.sharing.repository import roles_for_collections

logger = logging.getLogger(__name__)

_RRF_CANDIDATE_LIMIT = 200


def enqueue_embedding(collection_id: str, tenant_id: str) -> None:
    # Best-effort, même contrat que app.items.repository._enqueue_embedding
    # (Task 5) : le calcul d'embedding est déjà fail-open (app.collections.
    # jobs.embed_collection_task ne bloque jamais l'écriture sur un
    # fournisseur lent ou indisponible). L'ENQUEUE elle-même doit suivre le
    # même principe — sans quoi une file procrastinate injoignable
    # transformerait un simple "la collection restera cherchable par
    # trigram seul" en 500 sur toute création/modification de collection.
    # Import local (pas en tête de fichier) : évite un cycle d'import — même
    # raison que items (app.collections.jobs importe app.collections.models,
    # importé transitivement très tôt par app.db.core_table_names()).
    # Pas de préfixe `_` (contrairement à l'équivalent items) : cette
    # fonction est appelée depuis app.collections.routes (patch_collection),
    # pas seulement en interne à ce module — patch_collection a besoin de
    # conditionner l'enqueue à un changement de titre/description, logique
    # qui vit dans la route (il n'existe pas d'`update_collection` en
    # repository pour la porter, contrairement à items).
    from app.collections.jobs import embed_collection_task

    try:
        embed_collection_task.defer(collection_id=collection_id, tenant_id=tenant_id)
    except procrastinate.exceptions.ProcrastinateException:
        logger.exception(
            "échec de l'enqueue du job d'embedding pour la collection %s (l'écriture "
            "n'est pas affectée ; l'embedding restera NULL jusqu'au prochain write)",
            collection_id,
        )


def get_access_facts(col: Collection) -> AccessFacts:
    return AccessFacts(
        id=col.id,
        tenant_id=col.tenant_id,
        owner_id=col.owner_id,
        is_public=col.is_public,
        is_published=False,
    )


def get_collection(session: Session, *, tenant_id: str, collection_id: str) -> Collection | None:
    return session.scalar(
        select(Collection).where(Collection.tenant_id == tenant_id, Collection.id == collection_id)
    )


def create_collection(
    session: Session,
    *,
    tenant_id: str,
    owner_id: str,
    table_name: str,
    title: str,
    description: str,
    is_public: bool,
    pk_column: str,
    geometry_column: str | None,
    geometry_type: str | None,
    srid: int | None,
    feature_count: int | None = None,
) -> Collection:
    col = Collection(
        id=table_name,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=table_name,
        title=title,
        description=description,
        is_public=is_public,
        pk_column=pk_column,
        geometry_column=geometry_column,
        geometry_type=geometry_type,
        srid=srid,
        feature_count=feature_count,
    )
    session.add(col)
    session.flush()
    enqueue_embedding(col.id, tenant_id)
    return col


def list_visible_collections(
    session: Session,
    *,
    tenant_id: str,
    user_id: str | None,
    is_admin: bool,
    q: str | None = None,
) -> list[Collection]:
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not is_admin:
        if user_id is None:
            stmt = stmt.where(Collection.is_public.is_(True))
        else:
            shared_ids = (
                select(CollectionShare.collection_id)
                .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
                .where(GroupMember.user_id == user_id, CollectionShare.tenant_id == tenant_id)
            )
            stmt = stmt.where(
                Collection.is_public.is_(True)
                | (Collection.owner_id == user_id)
                | Collection.id.in_(shared_ids)
            )
    # Filtre de visibilité posé AVANT toute recherche (spec §Recherche
    # hybride + permissions), comme pour list_items.

    if q and session.get_bind().dialect.name == "postgresql":
        provider = get_embedding_provider()
        candidate_ids = hybrid_search_ids(
            session,
            base_stmt=stmt,
            id_column=Collection.id,
            text_columns=[Collection.title, Collection.description],
            embedding_column=Collection.embedding,
            query_text=q,
            query_vector=provider.embed(q),
            limit=_RRF_CANDIDATE_LIMIT,
        )
        rows = session.execute(select(Collection).where(Collection.id.in_(candidate_ids))).all()
        by_id = {c.id: c for (c,) in rows}
        return [by_id[i] for i in candidate_ids if i in by_id]

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Collection.title.ilike(like), Collection.description.ilike(like)))

    return list(session.scalars(stmt.order_by(Collection.title)).all())


def delete_collection(session: Session, col: Collection) -> None:
    session.delete(col)
    session.flush()


def get_collection_sharing(
    session: Session, *, tenant_id: str, collection_id: str
) -> list[CollectionShare]:
    return list(
        session.scalars(
            select(CollectionShare).where(
                CollectionShare.tenant_id == tenant_id,
                CollectionShare.collection_id == collection_id,
            )
        ).all()
    )


def set_collection_sharing(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
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

    session.execute(
        delete(CollectionShare).where(
            CollectionShare.tenant_id == tenant_id,
            CollectionShare.collection_id == collection_id,
        )
    )
    for group_id, role in groups:
        session.add(
            CollectionShare(
                collection_id=collection_id, group_id=group_id, tenant_id=tenant_id, role=role
            )
        )
    session.flush()
    return True


def _collection_permissions(
    col: Collection,
    *,
    current_user_id: str | None,
    roles: frozenset[str],
    actor_is_admin: bool,
) -> CollectionPermissions:
    is_owner = current_user_id is not None and col.owner_id == current_user_id

    def verdict(action: Action) -> bool:
        if action == "delete":
            return actor_is_admin
        base = decide(
            action=action,
            kind="collection",
            is_owner=is_owner,
            is_public=col.is_public,
            is_published=False,
            roles=roles,
            actor_is_admin=actor_is_admin,
        )
        return col.editable and base if action == "write" else base

    return CollectionPermissions(
        read=verdict("read"),
        write=verdict("write"),
        delete=verdict("delete"),
        share=verdict("share"),
    )


def collection_permissions_by_id(
    session: Session,
    *,
    tenant_id: str,
    current_user_id: str | None,
    actor_is_admin: bool,
    collections: list[Collection],
) -> dict[str, CollectionPermissions]:
    """Permissions de toute une page, avec **une** requête de rôles — pendant
    de `_permissions_by_id` dans `app.items.repository`. Anonyme (`current_user_id`
    absent) ne peut être ni propriétaire ni avoir de rôle : la requête de
    rôles est sautée."""
    roles_by_id = (
        roles_for_collections(
            session,
            tenant_id=tenant_id,
            user_id=current_user_id,
            collection_ids=[c.id for c in collections],
        )
        if current_user_id is not None
        else {}
    )
    return {
        c.id: _collection_permissions(
            c,
            current_user_id=current_user_id,
            roles=roles_by_id.get(c.id, frozenset()),
            actor_is_admin=actor_is_admin,
        )
        for c in collections
    }
