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


def test_list_items_scope_shared_is_empty(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Any")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert page.total == 0
    assert page.items == []


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
