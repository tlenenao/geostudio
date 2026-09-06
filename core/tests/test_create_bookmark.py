# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
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
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        bob = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-2",
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.user = user  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.bob = bob  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _app_body(title: str = "Cible") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1,
            "kind": "app",
            "layout": {"type": "grid", "breakpoints": {}, "items": []},
        },
    }


def _bookmark_body(app_id: str, title: str = "Ma vue") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1,
            "kind": "bookmark",
            "bookmark": {
                "appId": app_id,
                "pageId": "page-1",
                "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
                "extent": None,
                "crossFilter": {},
            },
        },
    }


def test_create_bookmark_avec_app_existante_et_lisible(client):
    app_item_id = client.post("/v1/configs", json=_app_body()).json()["itemId"]
    res = client.post("/v1/configs", json=_bookmark_body(app_item_id))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/v1/items/{item_id}").json()
    assert item["resourceType"] == "bookmark"


def test_create_bookmark_app_inexistante_rejetee(client):
    res = client.post("/v1/configs", json=_bookmark_body("inexistante"))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_app_non_lisible_rejetee_avec_meme_message(client):
    # Bob's app is private by default (Item.is_public defaults to False) —
    # alice (the caller) is neither its owner nor a group member.
    with client.session_factory() as session:
        from app.configs import repository as configs_repo
        from app.configs.schemas import BuilderConfig
        from app.items import repository as items_repo

        bob_app = items_repo.create_item(
            session,
            tenant_id=client.user.tenant_id,
            owner_id=client.bob.id,
            resource_type="app",
            title="App de Bob",
        )
        configs_repo.create_config(
            session,
            BuilderConfig(
                version=1, kind="app", layout={"type": "grid", "breakpoints": {}, "items": []}
            ),
            bob_app.id,
            tenant_id=client.user.tenant_id,
        )
        session.commit()
        bob_app_id = bob_app.id

    res = client.post("/v1/configs", json=_bookmark_body(bob_app_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_create_bookmark_cible_un_kind_non_app_rejetee(client):
    with client.session_factory() as session:
        from app.items import repository as items_repo

        map_item = items_repo.create_item(
            session,
            tenant_id=client.user.tenant_id,
            owner_id=client.user.id,
            resource_type="map",
            title="Une carte",
        )
        session.commit()
        map_item_id = map_item.id

    res = client.post("/v1/configs", json=_bookmark_body(map_item_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_update_bookmark_app_inexistante_rejetee(client):
    app_item_id = client.post("/v1/configs", json=_app_body()).json()["itemId"]
    created = client.post("/v1/configs", json=_bookmark_body(app_item_id))
    item_id = created.json()["itemId"]
    bad_config = {
        "version": 1,
        "kind": "bookmark",
        "bookmark": {"appId": "inexistante", "pageId": "page-1"},
    }
    res = client.put(f"/v1/configs/by-item/{item_id}", json=bad_config)
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"


def test_update_bookmark_by_config_id_app_inexistante_rejetee(client):
    # Same guard as test_update_bookmark_app_inexistante_rejetee, but via
    # PUT /configs/{config_id} (by config id, not by item) — the endpoint
    # that was missing the _validate_bookmark_payload wiring.
    app_item_id = client.post("/v1/configs", json=_app_body()).json()["itemId"]
    created = client.post("/v1/configs", json=_bookmark_body(app_item_id))
    config_id = created.json()["id"]
    bad_config = {
        "version": 1,
        "kind": "bookmark",
        "bookmark": {"appId": "inexistante", "pageId": "page-1"},
    }
    res = client.put(f"/v1/configs/{config_id}", json=bad_config)
    assert res.status_code == 422
    assert res.json()["detail"] == "app not found"
