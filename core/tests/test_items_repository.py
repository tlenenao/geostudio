import procrastinate
import pytest

from app.db import make_engine, make_session_factory, init_db
from app.items import repository as repo
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
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    return tenant, user


def test_create_and_get_item(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="My App",
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
        session, tenant_id=tenant.id, oidc_sub="sub-2",
        username="bob", email=None, first_name="", last_name="",
    )
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Mine")
    repo.create_item(session, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Theirs")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="mine", page=1, page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Mine"]


def test_list_items_scope_public(session, tenant_and_user):
    tenant, user = tenant_and_user
    published = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Published")
    repo.update_item(session, tenant_id=tenant.id, item_id=published.id, title=None, abstract=None, keywords=None, is_published=True)
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Draft")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="public", page=1, page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Published"]


def test_list_items_scope_shared_excludes_owned_items_with_no_shares(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Any")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert page.total == 0
    assert page.items == []


def test_list_items_scope_shared_and_all(session, tenant_and_user):
    from app.sharing.models import Group, GroupMember, ItemShare

    tenant, owner = tenant_and_user
    bob = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-bob",
        username="bob", email=None, first_name="", last_name="",
    )
    group = Group(id="g1", tenant_id=tenant.id, name="Reviewers", created_by=owner.id)
    session.add(group)
    session.flush()
    session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=tenant.id))

    owned_by_owner = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Owner's"
    )
    shared_with_bob = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Shared"
    )
    session.add(ItemShare(item_id=shared_with_bob.id, group_id=group.id, tenant_id=tenant.id, role="viewer"))
    public_item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Public"
    )
    public_item.is_public = True
    invisible = repo.create_item(
        session, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Invisible"
    )
    session.flush()

    shared_page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert shared_page.total == 1
    assert [i.title for i in shared_page.items] == ["Shared"]

    all_page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="all", page=1, page_size=12,
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
        session, tenant_id=tenant.id, current_user_id=bob.id,
        q=None, resource_type=None, scope="all", page=1, page_size=1,
    )
    assert first_of_two.total == 2
    assert len(first_of_two.items) == 1


def test_get_access_facts(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")

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
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incidents map")
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="dashboard", title="Sales dashboard")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q="incidents", resource_type=None, scope="all", page=1, page_size=12,
    )
    assert [i.title for i in page.items] == ["Incidents map"]

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type="dashboard", scope="all", page=1, page_size=12,
    )
    assert [i.title for i in page.items] == ["Sales dashboard"]


def test_update_item_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Old title")

    updated = repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title="New title", abstract="New abstract", keywords=["a", "b"], is_published=None,
    )
    assert updated is not None
    assert updated.title == "New title"
    assert updated.abstract == "New abstract"


def test_create_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    deferred = []
    from app.items import jobs as item_jobs
    monkeypatch.setattr(
        item_jobs.embed_item_task, "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]


def test_update_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")
    deferred = []
    from app.items import jobs as item_jobs
    monkeypatch.setattr(
        item_jobs.embed_item_task, "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title="Y", abstract=None, keywords=None, is_published=None,
    )
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]


def test_create_item_still_succeeds_when_the_embedding_enqueue_fails(session, tenant_and_user, monkeypatch):
    # Pins the actual contract _enqueue_embedding exists to guarantee: the
    # procrastinate App shared with the FastAPI process is never .open()ed,
    # so every unmocked .defer() raises AppNotOpen in practice. The write
    # itself must stay fail-open — the embedding enqueue is best-effort only.
    tenant, user = tenant_and_user
    from app.items import jobs as item_jobs

    def raise_app_not_open(**kwargs):
        raise procrastinate.exceptions.AppNotOpen()

    monkeypatch.setattr(item_jobs.embed_item_task, "defer", raise_app_not_open)
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")
    assert item is not None
    assert item.title == "X"
