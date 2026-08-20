# SPDX-License-Identifier: Apache-2.0
import procrastinate
import pytest

from app.collections import repository as repo
from app.db import Base, init_db, make_engine, make_session_factory
from app.search.providers import FakeProvider
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


def test_list_visible_collections_q_none_is_unchanged(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_collection(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c1",
        title="Communes",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    cols = repo.list_visible_collections(
        session, tenant_id=tenant.id, user_id=user.id, is_admin=False
    )
    assert [c.title for c in cols] == ["Communes"]


def test_create_collection_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    deferred = []
    from app.collections import jobs as collection_jobs

    monkeypatch.setattr(
        collection_jobs.embed_collection_task,
        "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    col = repo.create_collection(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c1",
        title="Communes",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    assert deferred == [{"collection_id": col.id, "tenant_id": tenant.id}]


def test_create_collection_still_succeeds_when_the_embedding_enqueue_fails(
    session,
    tenant_and_user,
    monkeypatch,
):
    # Pins the same contract as test_create_item_still_succeeds_when_the_
    # embedding_enqueue_fails (Task 5) : the procrastinate App shared with the
    # FastAPI process is never .open()ed, so every unmocked .defer() raises
    # AppNotOpen in practice. The write itself must stay fail-open.
    tenant, user = tenant_and_user
    from app.collections import jobs as collection_jobs

    def raise_app_not_open(**kwargs):
        raise procrastinate.exceptions.AppNotOpen()

    monkeypatch.setattr(collection_jobs.embed_collection_task, "defer", raise_app_not_open)
    col = repo.create_collection(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c1",
        title="Communes",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    assert col is not None
    assert col.title == "Communes"


# Le test de ranking/permissions hybride a besoin de Postgres réel (pg_trgm +
# pgvector) — fixture dédiée `pg_session`, même patron que Task 6.
@pytest.fixture()
def pg_session(pg_engine):
    from sqlalchemy import text

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE collections, users, tenants CASCADE"))


@pytest.mark.postgis
def test_list_visible_collections_hybrid_search_never_leaks_an_invisible_collection(
    pg_session,
    monkeypatch,
):
    tenant = get_or_create_default_tenant(pg_session)
    owner = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="owner",
        username="owner",
        email=None,
        first_name="",
        last_name="",
    )
    other = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="other",
        username="other",
        email=None,
        first_name="",
        last_name="",
    )
    private = repo.create_collection(
        pg_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="secret",
        title="Secret incidents",
        description="",
        is_public=False,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    private.embedding = [1.0] * 1536
    pg_session.flush()

    from app.collections import repository as collections_repo_module

    fake = FakeProvider(vectors={"incidents": [1.0] * 1536})
    monkeypatch.setattr(collections_repo_module, "get_embedding_provider", lambda: fake)

    cols = repo.list_visible_collections(
        pg_session,
        tenant_id=tenant.id,
        user_id=other.id,
        is_admin=False,
        q="incidents",
    )
    assert cols == []


@pytest.mark.postgis
def test_list_visible_collections_hybrid_search_ranks_semantic_match_ahead_of_weak_text_match(
    pg_session,
    monkeypatch,
):
    # Même correctif que Task 4/Task 6 (RRF tie) : sans un troisième
    # candidat non-embeddé qui dispute le rang trigramme, "Sujet totalement
    # différent" (rang 1 vecteur seul) et "incidents" (rang 1 trigramme
    # seul) arrivent à égalité RRF stricte — vérifié empiriquement contre
    # Postgres réel avant d'ajouter ce filler (le test échouait par ordre
    # d'insertion, pas par un vrai défaut de list_visible_collections).
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )

    close_vector = [1.0] * 1536
    query_vector = [0.99] * 1536
    far_vector = [-1.0] * 1536

    semantically_close = repo.create_collection(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c_close",
        title="Sujet totalement différent",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    semantically_close.embedding = close_vector
    weak_text_match = repo.create_collection(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c_weak",
        title="incidents",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    weak_text_match.embedding = far_vector
    repo.create_collection(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        table_name="c_filler",
        title="incidents voirie",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    pg_session.flush()

    from app.collections import repository as collections_repo_module

    fake = FakeProvider(vectors={"incidents voirie": query_vector})
    monkeypatch.setattr(collections_repo_module, "get_embedding_provider", lambda: fake)

    cols = repo.list_visible_collections(
        pg_session,
        tenant_id=tenant.id,
        user_id=user.id,
        is_admin=False,
        q="incidents voirie",
    )
    titles = [c.title for c in cols]
    assert titles.index("Sujet totalement différent") < titles.index("incidents")
