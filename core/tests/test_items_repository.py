# SPDX-License-Identifier: Apache-2.0
import procrastinate
import pytest
from sqlalchemy import text

from app.db import Base, init_db, make_engine, make_session_factory
from app.items import repository as repo
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
        oidc_sub="sub-1",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


@pytest.fixture()
def pg_session(pg_engine):
    # `session`/`tenant_and_user` ci-dessus créent un moteur SQLite en
    # mémoire — insuffisant pour les tests `postgis` de ce module : la
    # branche hybride de list_items() ne s'active que sur dialect ==
    # "postgresql", et hybrid_search_ids() utilise func.similarity()
    # (pg_trgm) et .cosine_distance() (pgvector), tous deux absents de
    # SQLite. Même pattern que test_search_ranking.py/test_items_jobs.py :
    # un moteur PostGIS réel (pg_engine, skip via CORE_TEST_DATABASE_URL
    # absent) avec TRUNCATE en teardown.
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="sub-1",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


def test_create_and_get_item(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="My App",
    )

    read = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert read is not None
    assert read.title == "My App"
    assert read.owner == "alice"
    assert read.resourceType == "app"
    assert read.configId is None  # no config lookup from app.items — see plan Architecture
    assert read.isPublished is False


def test_get_item_missing_returns_none(session, tenant_and_user):
    tenant, _ = tenant_and_user
    assert repo.get_item(session, tenant_id=tenant.id, item_id="nope") is None


def test_list_items_scope_mine(session, tenant_and_user):
    tenant, user = tenant_and_user
    other = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-2",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Mine"
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Theirs"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="mine",
        page=1,
        page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Mine"]


def test_list_items_scope_public(session, tenant_and_user):
    tenant, user = tenant_and_user
    published = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Published"
    )
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=published.id,
        title=None,
        abstract=None,
        keywords=None,
        is_published=True,
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Draft"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="public",
        page=1,
        page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Published"]


def test_list_items_scope_shared_excludes_owned_items_with_no_shares(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Any"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="shared",
        page=1,
        page_size=12,
    )
    assert page.total == 0
    assert page.items == []


def test_list_items_scope_shared_and_all(session, tenant_and_user):
    from app.sharing.models import Group, GroupMember, ItemShare

    tenant, owner = tenant_and_user
    bob = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-bob",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=tenant.id))

    # Negative control: owner's own item, not shared with bob, not public —
    # must not leak into bob's "shared"/"all" scope results (asserted below
    # by title, the created row itself is never referenced again).
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Owner's"
    )
    shared_with_bob = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Shared"
    )
    session.add(
        ItemShare(item_id=shared_with_bob.id, group_id=group.id, tenant_id=tenant.id, role="viewer")
    )
    public_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Public"
    )
    public_item.is_public = True
    # Negative control: neither shared with bob nor public — must not leak
    # into bob's "shared"/"all" scope results (asserted below by title).
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Invisible"
    )
    session.flush()

    shared_page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=bob.id,
        q=None,
        resource_type=None,
        scope="shared",
        page=1,
        page_size=12,
    )
    assert shared_page.total == 1
    assert [i.title for i in shared_page.items] == ["Shared"]

    all_page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=bob.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
    )
    assert all_page.total == 2
    titles = {i.title for i in all_page.items}
    assert titles == {"Shared", "Public"}
    assert "Invisible" not in titles
    assert "Owner's" not in titles  # bob doesn't own it, isn't shared, not public

    # Pagination correctness (spec §7): a small page_size must still report the
    # true total and return exactly the items for that page, not an
    # in-memory-filtered approximation.
    first_of_two = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=bob.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=1,
    )
    assert first_of_two.total == 2
    assert len(first_of_two.items) == 1


def test_get_access_facts(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )

    facts = repo.get_access_facts(session, tenant_id=tenant.id, item_id=item.id)
    assert facts is not None
    assert facts.owner_id == user.id
    assert facts.is_public is False
    assert facts.is_published is False


def test_get_access_facts_missing_returns_none(session, tenant_and_user):
    tenant, _ = tenant_and_user
    assert repo.get_access_facts(session, tenant_id=tenant.id, item_id="nope") is None


def test_list_items_search_and_type_filter(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incidents map"
    )
    repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="dashboard",
        title="Sales dashboard",
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q="incidents",
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
    )
    assert [i.title for i in page.items] == ["Incidents map"]

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type="dashboard",
        scope="all",
        page=1,
        page_size=12,
    )
    assert [i.title for i in page.items] == ["Sales dashboard"]


def test_list_items_sort_title_asc(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Zorro"
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Alpha"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        sort="title_asc",
    )
    assert [i.title for i in page.items] == ["Alpha", "Zorro"]


def test_list_items_sort_title_desc(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Alpha"
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Zorro"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        sort="title_desc",
    )
    assert [i.title for i in page.items] == ["Zorro", "Alpha"]


def test_list_items_sort_date_asc(session, tenant_and_user):
    tenant, user = tenant_and_user
    first = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="First"
    )
    second = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Second"
    )
    # created_at par défaut vient de datetime.now(UTC) — pour un test
    # déterministe (pas tributaire de l'horloge et de la résolution du
    # dialecte), on pose explicitement des valeurs bien distinctes.
    from datetime import UTC, datetime

    first_item = session.get(type(first), first.id)
    second_item = session.get(type(second), second.id)
    first_item.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    second_item.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    session.flush()

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        sort="date_asc",
    )
    assert [i.title for i in page.items] == ["First", "Second"]


def test_list_items_sort_updated_desc(session, tenant_and_user):
    tenant, user = tenant_and_user
    first = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="First"
    )
    second = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Second"
    )
    from datetime import UTC, datetime

    first_item = session.get(type(first), first.id)
    second_item = session.get(type(second), second.id)
    first_item.updated_at = datetime(2020, 1, 5, tzinfo=UTC)
    second_item.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    session.flush()

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        sort="updated_desc",
    )
    assert [i.title for i in page.items] == ["First", "Second"]


def test_list_items_default_sort_unchanged_without_explicit_sort(session, tenant_and_user):
    # Non-régression explicite : sans `sort`, l'ordre par défaut
    # (created_at desc) doit rester identique au comportement actuel.
    tenant, user = tenant_and_user
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Mine"
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Mine 2"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
    )
    assert [i.title for i in page.items] == ["Mine 2", "Mine"]


def test_list_items_filter_by_owner(session, tenant_and_user):
    tenant, user = tenant_and_user
    bob = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-bob",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Alice item"
    )
    bob_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=bob.id, resource_type="app", title="Bob item"
    )
    # Publié pour être visible par alice sous scope="all" (le test isole
    # l'effet du filtre owner, pas la visibilité elle-même — cf. le test
    # jumeau ci-dessous pour la composition owner+scope restrictif).
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=bob_item.id,
        title=None,
        abstract=None,
        keywords=None,
        is_published=True,
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        owner="bob",
    )
    assert [i.title for i in page.items] == ["Bob item"]


def test_list_items_filter_by_owner_respects_scope(session, tenant_and_user):
    # owner ne doit jamais réintroduire un item invisible par ailleurs :
    # scope="mine" avec owner="bob" (!= utilisateur courant) doit rester vide.
    tenant, user = tenant_and_user
    bob = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-bob",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=bob.id, resource_type="app", title="Bob item"
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="mine",
        page=1,
        page_size=12,
        owner="bob",
    )
    assert page.items == []
    assert page.total == 0


def test_list_items_filter_by_keyword_and(session, tenant_and_user):
    tenant, user = tenant_and_user
    a = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="A"
    )
    b = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="B"
    )
    c = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="C"
    )
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=a.id,
        title=None,
        abstract=None,
        keywords=["a", "b"],
        is_published=None,
    )
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=b.id,
        title=None,
        abstract=None,
        keywords=["a"],
        is_published=None,
    )
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=c.id,
        title=None,
        abstract=None,
        keywords=["b", "c"],
        is_published=None,
    )

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        keywords=["a"],
    )
    assert {i.title for i in page.items} == {"A", "B"}

    page = repo.list_items(
        session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q=None,
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        keywords=["a", "b"],
    )
    assert {i.title for i in page.items} == {"A"}


def test_update_item_patches_keywords_and_get_item_returns_them(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )

    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title=None,
        abstract=None,
        keywords=["geo", "risques"],
        is_published=None,
    )

    result = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert result.keywords == ["geo", "risques"]


def test_get_item_defaults_keywords_to_empty_list(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )

    result = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert result.keywords == []


def test_update_item_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Old title"
    )

    updated = repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title="New title",
        abstract="New abstract",
        keywords=["a", "b"],
        is_published=None,
    )
    assert updated is not None
    assert updated.title == "New title"
    assert updated.abstract == "New abstract"


def test_create_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    deferred = []
    from app.items import jobs as item_jobs

    monkeypatch.setattr(
        item_jobs.embed_item_task,
        "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]


def test_update_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )
    deferred = []
    from app.items import jobs as item_jobs

    monkeypatch.setattr(
        item_jobs.embed_item_task,
        "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title="Y",
        abstract=None,
        keywords=None,
        is_published=None,
    )
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]


@pytest.mark.postgis
def test_list_items_hybrid_search_ranks_semantic_match_ahead_of_weak_text_match(
    pg_session,
    pg_tenant_and_user,
    monkeypatch,
):
    tenant, user = pg_tenant_and_user

    close_vector = [1.0] * 1536
    query_vector = [0.99] * 1536
    far_vector = [-1.0] * 1536

    semantically_close = repo.create_item(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="Sujet totalement différent",
    )
    semantically_close.embedding = close_vector
    weak_text_match = repo.create_item(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="incidents",
    )
    weak_text_match.embedding = far_vector
    # Troisième item, meilleur match trigram qu'"incidents" seul et pas
    # encore embeddé — même correctif que test_search_ranking.py::
    # test_hybrid_search_ids_ranks_a_vector_match_ahead_of_a_weak_text_match
    # (Task 4) : sans lui, "Sujet totalement différent" (rang 1 vecteur
    # seul) et "incidents" (rang 1 trigramme seul) arrivent à égalité RRF
    # stricte (chacun 1/61, présent dans une seule liste), et l'ordre
    # observé dépend alors de l'ordre d'insertion dans reciprocal_rank_
    # fusion() plutôt que d'un vrai différentiel de pertinence — vérifié
    # empiriquement : la version sans filler de ce test échouait
    # (['incidents', 'Sujet totalement différent']) malgré une implémentation
    # correcte de list_items(). Cet item pousse "incidents" au rang 2
    # trigramme, départageant les deux candidats sans ambiguïté.
    repo.create_item(
        pg_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="incidents voirie",
    )
    pg_session.flush()

    from app.items import repository as items_repo_module

    fake = FakeProvider(vectors={"incidents voirie": query_vector})
    monkeypatch.setattr(items_repo_module, "get_embedding_provider", lambda: fake)

    page = repo.list_items(
        pg_session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q="incidents voirie",
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
    )
    titles = [i.title for i in page.items]
    assert titles.index("Sujet totalement différent") < titles.index("incidents")


@pytest.mark.postgis
def test_list_items_hybrid_search_respects_explicit_sort(
    pg_session, pg_tenant_and_user, monkeypatch
):
    # Un tri explicite (date/titre) posé en même temps que `q` doit écraser
    # l'ordre RRF (pertinence) — le chemin hybride doit trier les lignes
    # récupérées au lieu de suivre l'ordre de candidate_ids (spec §1.1).
    tenant, user = pg_tenant_and_user
    query_vector = [0.5] * 1536
    z_item = repo.create_item(
        pg_session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Z incidents"
    )
    z_item.embedding = [1.0] * 1536  # meilleur match vectoriel que a_item
    a_item = repo.create_item(
        pg_session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="A incidents"
    )
    a_item.embedding = [-1.0] * 1536
    pg_session.flush()

    from app.items import repository as items_repo_module

    fake = FakeProvider(vectors={"incidents": query_vector})
    monkeypatch.setattr(items_repo_module, "get_embedding_provider", lambda: fake)

    # Sans tri explicite : l'ordre RRF place Z (meilleur vecteur) devant A.
    page = repo.list_items(
        pg_session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q="incidents",
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
    )
    assert [i.title for i in page.items].index("Z incidents") < [i.title for i in page.items].index(
        "A incidents"
    )

    # Avec sort="title_asc" explicite : l'ordre RRF est écrasé.
    page = repo.list_items(
        pg_session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q="incidents",
        resource_type=None,
        scope="all",
        page=1,
        page_size=12,
        sort="title_asc",
    )
    assert [i.title for i in page.items] == ["A incidents", "Z incidents"]


@pytest.mark.postgis
def test_list_items_hybrid_search_never_leaks_an_invisible_item(
    pg_session, pg_tenant_and_user, monkeypatch
):
    tenant, user = pg_tenant_and_user
    other = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="sub-other",
        username="other",
        email=None,
        first_name="",
        last_name="",
    )
    invisible = repo.create_item(
        pg_session,
        tenant_id=tenant.id,
        owner_id=other.id,
        resource_type="app",
        title="incidents secrets",
    )
    invisible.embedding = [1.0] * 1536
    pg_session.flush()

    from app.items import repository as items_repo_module

    fake = FakeProvider(vectors={"incidents": [1.0] * 1536})
    monkeypatch.setattr(items_repo_module, "get_embedding_provider", lambda: fake)

    page = repo.list_items(
        pg_session,
        tenant_id=tenant.id,
        current_user_id=user.id,
        q="incidents",
        resource_type=None,
        scope="mine",
        page=1,
        page_size=12,
    )
    assert page.items == []


def test_create_item_still_succeeds_when_the_embedding_enqueue_fails(
    session, tenant_and_user, monkeypatch
):
    # Pins the actual contract _enqueue_embedding exists to guarantee: the
    # procrastinate App shared with the FastAPI process is never .open()ed,
    # so every unmocked .defer() raises AppNotOpen in practice. The write
    # itself must stay fail-open — the embedding enqueue is best-effort only.
    tenant, user = tenant_and_user
    from app.items import jobs as item_jobs

    def raise_app_not_open(**kwargs):
        raise procrastinate.exceptions.AppNotOpen()

    monkeypatch.setattr(item_jobs.embed_item_task, "defer", raise_app_not_open)
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X"
    )
    assert item is not None
    assert item.title == "X"


def test_create_item_increments_items_created_counter(session, tenant_and_user, monkeypatch):
    from unittest.mock import Mock

    tenant, user = tenant_and_user
    mock_counter = Mock()
    monkeypatch.setattr(repo, "_items_created_counter", mock_counter)

    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incident"
    )

    mock_counter.add.assert_called_once_with(1)


def test_update_item_increments_published_counter_only_when_publishing(
    session, tenant_and_user, monkeypatch
):
    from unittest.mock import Mock

    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incident"
    )
    mock_counter = Mock()
    monkeypatch.setattr(repo, "_items_published_counter", mock_counter)

    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title=None,
        abstract=None,
        keywords=None,
        is_published=None,
    )
    mock_counter.add.assert_not_called()

    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title=None,
        abstract=None,
        keywords=None,
        is_published=False,
    )
    mock_counter.add.assert_not_called()

    repo.update_item(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        title=None,
        abstract=None,
        keywords=None,
        is_published=True,
    )
    mock_counter.add.assert_called_once_with(1)


def test_list_published_items_returns_only_published(session, tenant_and_user):
    tenant, user = tenant_and_user
    published = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Publie"
    )
    published.is_published = True
    repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Brouillon"
    )
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, page=1, page_size=12)
    assert [i.title for i in page.items] == ["Publie"]


def test_list_published_items_filters_by_resource_type(session, tenant_and_user):
    tenant, user = tenant_and_user
    app_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="App"
    )
    app_item.is_published = True
    dash_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="dashboard", title="Dashboard"
    )
    dash_item.is_published = True
    session.commit()

    page = repo.list_published_items(
        session, tenant_id=tenant.id, resource_type="dashboard", page=1, page_size=12
    )
    assert [i.title for i in page.items] == ["Dashboard"]


def test_list_published_items_filters_by_tag(session, tenant_and_user):
    tenant, user = tenant_and_user
    tagged = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Avec tag"
    )
    tagged.is_published = True
    tagged.keywords = ["risques"]
    untagged = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Sans tag"
    )
    untagged.is_published = True
    session.commit()

    page = repo.list_published_items(
        session, tenant_id=tenant.id, tag="risques", page=1, page_size=12
    )
    assert [i.title for i in page.items] == ["Avec tag"]


def test_list_published_items_paginates(session, tenant_and_user):
    tenant, user = tenant_and_user
    for i in range(3):
        item = repo.create_item(
            session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title=f"Item {i}"
        )
        item.is_published = True
    session.commit()

    page = repo.list_published_items(session, tenant_id=tenant.id, page=1, page_size=2)
    assert page.total == 3
    assert len(page.items) == 2
    assert page.page == 1
    assert page.pageSize == 2


def test_list_published_items_defaults_to_default_tenant(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Publie"
    )
    item.is_published = True
    session.commit()

    page = repo.list_published_items(session, page=1, page_size=12)
    assert [i.title for i in page.items] == ["Publie"]
