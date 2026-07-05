import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        # Repository functions only flush now; commit here to stand in for
        # "a prior successful request that provisioned this tenant/user".
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _seed_item(client, title="My App") -> str:
    # No linked Config/ConfigRevision needed here: these routes never look up
    # configId (see plan Architecture — app.items must not import app.configs).
    with client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=client.tenant.id, owner_id=client.user.id,
            resource_type="app", title=title,
        )
        # create_item only flushes now; this block bypasses the request
        # boundary, so commit explicitly to persist the seed row.
        session.commit()
        return item.id


def test_get_item_returns_it(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "My App"
    assert body["owner"] == "alice"


def test_get_item_missing_returns_404(client):
    assert client.get("/items/nope").status_code == 404


def test_list_items_default_scope_all(client):
    _seed_item(client, title="One")
    _seed_item(client, title="Two")
    response = client.get("/items")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["pageSize"] == 12


def test_patch_item_updates_title(client):
    item_id = _seed_item(client)
    response = client.patch(f"/items/{item_id}", json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


def test_patch_item_missing_returns_404(client):
    assert client.patch("/items/nope", json={"title": "x"}).status_code == 404
