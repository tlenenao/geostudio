# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.models import Tenant
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
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
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
    yield test_client
    engine.dispose()


def _create_config(client) -> dict:
    body = {
        "kind": "app",
        "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 4, "h": 4}]},
    }
    response = client.post("/configs", json={"title": "My App", "config": body})
    assert response.status_code == 201, response.text
    return response.json()


def test_public_get_published_item_requires_no_auth(client):
    created = _create_config(client)
    client.patch(f"/items/{created['itemId']}", json={"isPublished": True})

    # Deliberately clear the auth override to prove no Authorization header is needed.
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/items/{created['itemId']}")
    assert response.status_code == 200
    assert response.json()["title"] == "My App"


def test_public_get_unpublished_item_returns_404(client):
    created = _create_config(client)
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/items/{created['itemId']}")
    assert response.status_code == 404


def test_public_get_nonexistent_item_returns_404_same_as_unpublished(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items/does-not-exist")
    assert response.status_code == 404


def test_public_get_config_by_item_for_published_item(client):
    created = _create_config(client)
    client.patch(f"/items/{created['itemId']}", json={"isPublished": True})
    del client.app.dependency_overrides[get_current_user]

    response = client.get(f"/public/configs/by-item/{created['itemId']}")
    assert response.status_code == 200
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_public_get_config_by_item_for_unpublished_item_returns_404(client):
    created = _create_config(client)
    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/configs/by-item/{created['itemId']}")
    assert response.status_code == 404


def _create_other_tenant_published_item(client) -> str:
    with client.session_factory() as session:
        other_tenant = Tenant(id="other", slug="other", name="Other")
        session.add(other_tenant)
        session.flush()
        bob = get_or_create_user(
            session,
            tenant_id="other",
            oidc_sub="sub-other",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        other_item = items_repo.create_item(
            session,
            tenant_id="other",
            owner_id=bob.id,
            resource_type="app",
            title="Secret d'un autre tenant",
        )
        other_item.is_published = True
        other_item_id = other_item.id
        session.commit()
    return other_item_id


def test_public_get_item_by_id_does_not_leak_across_tenants(client):
    # SP-42/F-coeur-contenu-01 : GET /public/items/{item_id} ne doit jamais
    # servir un item publié d'un AUTRE tenant, même quand son id est connu.
    other_item_id = _create_other_tenant_published_item(client)

    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/items/{other_item_id}")
    assert response.status_code == 404


def test_public_get_config_by_item_does_not_leak_across_tenants(client):
    # SP-42/F-coeur-contenu-01 : GET /public/configs/by-item/{item_id} ne doit
    # jamais servir la config d'un item publié d'un AUTRE tenant.
    other_item_id = _create_other_tenant_published_item(client)

    del client.app.dependency_overrides[get_current_user]
    response = client.get(f"/public/configs/by-item/{other_item_id}")
    assert response.status_code == 404
