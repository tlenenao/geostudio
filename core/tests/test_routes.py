# SPDX-License-Identifier: Apache-2.0
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user
from app.configs import routes
from app.configs.models import Config
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
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
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
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


def _config_body(widget: str = "map") -> dict:
    return {
        "kind": "app",
        "layout": {"type": "grid", "items": [{"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}]},
    }


def _create(client, widget: str = "map") -> dict:
    response = client.post("/configs", json={"title": "My App", "config": _config_body(widget)})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_config_creates_a_real_item_owned_by_the_authenticated_user(client):
    body = _create(client)
    assert body["version"] == 1
    with client.session_factory() as session:
        item = session.get(Item, body["itemId"])
        assert item is not None
        assert item.owner_id == client.user.id
        assert item.title == "My App"


def test_get_config_returns_it(client):
    created = _create(client)
    response = client.get(f"/configs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_get_missing_config_returns_404(client):
    assert client.get("/configs/nope").status_code == 404


def test_put_updates_and_bumps_version(client):
    created = _create(client, widget="map")
    response = client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "table"


def test_put_missing_config_returns_404(client):
    assert client.put("/configs/nope", json=_config_body()).status_code == 404


def test_revisions_listed(client):
    created = _create(client)
    client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    response = client.get(f"/configs/{created['id']}/revisions")
    assert response.status_code == 200
    assert [r["version"] for r in response.json()] == [1, 2]


def test_rollback_restores_revision(client):
    created = _create(client, widget="map")
    client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    response = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_rollback_missing_returns_404(client):
    created = _create(client)
    assert (
        client.post(f"/configs/{created['id']}/rollback", json={"version": 99}).status_code == 404
    )


def test_delete_config_removes_config_and_item(client):
    created = _create(client)
    config_id = created["id"]
    item_id = created["itemId"]

    response = client.delete(f"/configs/{config_id}")
    assert response.status_code == 204
    assert client.get(f"/configs/{config_id}").status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_missing_config_returns_404(client):
    assert client.delete("/configs/nope").status_code == 404


def test_get_config_by_item(client):
    created = _create(client)
    item_id = created["itemId"]
    response = client.get(f"/configs/by-item/{item_id}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_config_by_item_missing_returns_404(client):
    assert client.get("/configs/by-item/nope").status_code == 404


def test_delete_by_item_removes_config_and_item(client):
    created = _create(client)
    item_id = created["itemId"]

    response = client.delete(f"/configs/by-item/{item_id}")
    assert response.status_code == 204
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_by_item_missing_returns_404(client):
    assert client.delete("/configs/by-item/nope").status_code == 404


def test_delete_item_directly_removes_config_and_item(client):
    created = _create(client)
    config_id, item_id = created["id"], created["itemId"]

    response = client.delete(f"/items/{item_id}")
    assert response.status_code == 204
    assert client.get(f"/configs/{config_id}").status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is None


def test_delete_item_missing_returns_404(client):
    assert client.delete("/items/nope").status_code == 404


def _map_config() -> dict:
    return {
        "kind": "map",
        "map": {
            "basemap": {"style": "https://demotiles.maplibre.org/style.json"},
            "view": {"center": [2.35, 48.85], "zoom": 5},
            "layers": [
                {
                    "id": "l1",
                    "title": "Communes",
                    "visible": True,
                    "kind": "vector",
                    "tilesUrl": "https://martin/communes/{z}/{x}/{y}",
                    "sourceLayer": "communes",
                },
            ],
        },
    }


def test_map_config_round_trips_through_create_and_get(client):
    response = client.post(
        "/configs",
        json={"title": "Ma carte", "config": _map_config()},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["kind"] == "map"

    fetched = client.get(f"/configs/{created['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["config"]["kind"] == "map"
    assert body["config"]["map"]["layers"][0]["sourceLayer"] == "communes"

    # by-item GET (used by the front's getMapConfig) also returns the map
    item_id = created["itemId"]
    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    assert by_item.json()["config"]["map"]["view"]["zoom"] == 5


def test_map_config_can_be_updated(client):
    created = client.post(
        "/configs",
        json={"title": "Ma carte", "config": _map_config()},
    ).json()
    updated = _map_config()
    updated["map"]["view"]["zoom"] = 9
    response = client.put(f"/configs/{created['id']}", json=updated)
    assert response.status_code == 200
    assert response.json()["config"]["map"]["view"]["zoom"] == 9


def test_put_config_by_item_updates_map(client):
    # Create a map item via the normal flow.
    create = client.post(
        "/configs",
        json={
            "title": "Ma carte",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [2.4, 46.6], "zoom": 5},
                    "layers": [],
                },
            },
        },
    )
    assert create.status_code == 201
    item_id = create.json()["itemId"]

    # Update it by item id.
    put = client.put(
        f"/configs/by-item/{item_id}",
        json={
            "kind": "map",
            "map": {
                "basemap": {"style": "https://demo/style.json"},
                "view": {"center": [1.0, 47.0], "zoom": 8},
                "layers": [
                    {
                        "id": "a",
                        "title": "A",
                        "visible": True,
                        "kind": "feature",
                        "url": "https://fs/a",
                    }
                ],
            },
        },
    )
    assert put.status_code == 200
    body = put.json()
    # ConfigRead nests the builder config under "config"; the map payload is config.map.
    assert body["config"]["map"]["view"]["zoom"] == 8
    assert len(body["config"]["map"]["layers"]) == 1

    # Confirm persistence via GET by-item.
    got = client.get(f"/configs/by-item/{item_id}")
    assert got.json()["config"]["map"]["layers"][0]["id"] == "a"


def test_put_config_by_item_404_when_missing(client):
    resp = client.put(
        "/configs/by-item/does-not-exist",
        json={
            "kind": "map",
            "map": {"basemap": {"style": "s"}, "view": {"center": [0, 0], "zoom": 1}, "layers": []},
        },
    )
    assert resp.status_code == 404


def test_map_config_round_trips_tiles3d_layer_terrain_and_camera(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte 3D",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [2.35, 48.85], "zoom": 5, "pitch": 45, "bearing": 90},
                    "layers": [
                        {
                            "id": "bldg",
                            "title": "Bâtiments",
                            "visible": True,
                            "kind": "tiles3d",
                            "url": "https://example.test/tileset.json",
                        },
                    ],
                    "terrain": {
                        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
                        "encoding": "terrarium",
                        "exaggeration": 1.5,
                    },
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]["map"]
    assert body["view"]["pitch"] == 45
    assert body["view"]["bearing"] == 90
    assert body["layers"][0] == {
        "id": "bldg",
        "title": "Bâtiments",
        "visible": True,
        "kind": "tiles3d",
        "tilesUrl": None,
        "sourceLayer": None,
        "url": "https://example.test/tileset.json",
        "opacity": None,
        "deckType": None,
        "dataUrl": None,
        "paint": None,
        "props": None,
        "popup": None,
        "collectionId": None,
        "geometryKind": None,
        "pkColumn": None,
    }
    assert body["terrain"] == {
        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
        "encoding": "terrarium",
        "exaggeration": 1.5,
    }


def test_map_config_defaults_pitch_bearing_terrain_when_absent(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte plate",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [0, 0], "zoom": 1},
                    "layers": [],
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]
    body = client.get(f"/configs/by-item/{item_id}").json()["config"]["map"]
    assert body["view"]["pitch"] is None
    assert body["view"]["bearing"] is None
    assert body["terrain"] is None


def test_create_config_is_atomic_when_a_later_step_fails(client, monkeypatch):
    """If create_config raises AFTER create_item has already run, the whole
    request must roll back — no orphaned Item may survive. This proves the
    single-commit-per-request boundary (repo functions flush, the request
    owns the commit) actually protects atomicity."""

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure after create_item")

    monkeypatch.setattr(routes.repo, "create_config", boom)

    with pytest.raises(RuntimeError, match="simulated failure after create_item"):
        client.post("/configs", json={"title": "My App", "config": _config_body()})

    # A fresh session must see zero Item rows: create_item's write was rolled
    # back with the rest of the failed request, not left behind as an orphan.
    with client.session_factory() as session:
        assert session.scalars(select(Item)).all() == []


def test_create_config_writes_audit_log(client):
    _create(client)
    with client.session_factory() as session:
        rows = session.scalars(select(AuditLog)).all()
        actions = {r.action for r in rows}
        assert "config.create" in actions
        assert "item.create" in actions


@pytest.fixture()
def client_with_real_auth(monkeypatch):
    """Like `client`, but deliberately does NOT override get_current_user, so
    the real dependency (mock-mode resolution, header parsing) runs
    end-to-end through the HTTP request. This is what proves authentication
    is genuinely wired into the route rather than always being bypassed by
    the `client` fixture's override."""
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    # Note: get_current_user is deliberately NOT overridden here.

    test_client = TestClient(app)
    yield test_client
    engine.dispose()


def test_create_config_without_authorization_header_is_rejected(client_with_real_auth):
    # No Authorization header at all: get_current_user checks
    # `authorization.startswith("Bearer ")` before even looking at mock mode,
    # so this must 401 regardless of CORE_AUTH_MODE.
    response = client_with_real_auth.post(
        "/configs",
        json={"title": "My App", "config": _config_body()},
    )
    assert response.status_code == 401


def _other_tenant_user(client) -> object:
    """Provision a second tenant with its own user, distinct from the
    `client` fixture's default tenant/user ("alice"). Used to prove
    cross-tenant delete requests are rejected."""
    with client.session_factory() as session:
        tenant = Tenant(id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other")
        session.add(tenant)
        session.flush()
        mallory = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-mallory",
            username="mallory",
            email="mallory@example.com",
            first_name="Mallory",
            last_name="Doe",
        )
        session.commit()
        session.refresh(mallory)
    return mallory


def _same_tenant_stranger(client) -> object:
    with client.session_factory() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=client.tenant.id,
            oidc_sub="sub-stranger",
            username="stranger",
            email="stranger@example.com",
            first_name="Stranger",
            last_name="Doe",
        )
        session.commit()
        session.refresh(stranger)
    return stranger


def test_get_config_invisible_to_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/{created['id']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_put_config_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.put(f"/configs/{created['id']}", json=_config_body())
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_revisions_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/{created['id']}/revisions")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_rollback_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_delete_config_by_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.delete(f"/configs/{created['id']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, created["itemId"]) is not None


def test_get_config_by_item_invisible_to_stranger_returns_404(client):
    created = _create(client)
    stranger = _same_tenant_stranger(client)
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.get(f"/configs/by-item/{created['itemId']}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_group_editor_can_update_config(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    created = _create(client)
    with client.session_factory() as session:
        editor = get_or_create_user(
            session,
            tenant_id=client.tenant.id,
            oidc_sub="sub-editor",
            username="editor",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(
            id="g1", tenant_id=client.tenant.id, name="Editors", created_by=client.user.id
        )
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=editor.id, tenant_id=client.tenant.id))
        session.add(
            ItemShare(
                item_id=created["itemId"],
                group_id=group.id,
                tenant_id=client.tenant.id,
                role="editor",
            )
        )
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: editor
    try:
        response = client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 200


def test_group_viewer_cannot_update_config_returns_403(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    created = _create(client)
    with client.session_factory() as session:
        viewer = get_or_create_user(
            session,
            tenant_id=client.tenant.id,
            oidc_sub="sub-viewer",
            username="viewer",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(
            id="g-viewer", tenant_id=client.tenant.id, name="Viewers", created_by=client.user.id
        )
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=viewer.id, tenant_id=client.tenant.id))
        session.add(
            ItemShare(
                item_id=created["itemId"],
                group_id=group.id,
                tenant_id=client.tenant.id,
                role="viewer",
            )
        )
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: viewer
    try:
        response = client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 403


def test_delete_config_cross_tenant_returns_404_and_leaves_data_intact(client):
    created = _create(client)
    config_id, item_id = created["id"], created["itemId"]
    mallory = _other_tenant_user(client)

    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.delete(f"/configs/{config_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user

    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is not None
        assert session.get(Config, config_id) is not None
    assert client.get(f"/configs/{config_id}").status_code == 200


def test_delete_config_by_item_cross_tenant_returns_404_and_leaves_data_intact(client):
    created = _create(client)
    config_id, item_id = created["id"], created["itemId"]
    mallory = _other_tenant_user(client)

    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.delete(f"/configs/by-item/{item_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user

    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is not None
        assert session.get(Config, config_id) is not None
    assert client.get(f"/configs/by-item/{item_id}").status_code == 200


def test_delete_item_cross_tenant_returns_404_and_leaves_data_intact(client):
    created = _create(client)
    config_id, item_id = created["id"], created["itemId"]
    mallory = _other_tenant_user(client)

    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.delete(f"/items/{item_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user

    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.get(Item, item_id) is not None
        assert session.get(Config, config_id) is not None
    assert client.get(f"/configs/{config_id}").status_code == 200


def test_create_config_with_bearer_token_succeeds_in_mock_mode(client_with_real_auth):
    # Mock mode accepts any bearer token as long as the header is present
    # and prefixed with "Bearer ". This proves get_current_user really runs
    # (and succeeds) through the full HTTP stack, not just when overridden.
    response = client_with_real_auth.post(
        "/configs",
        json={"title": "My App", "config": _config_body()},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 201, response.text


def test_get_config_by_item_with_mode_runtime_increments_counter(client, monkeypatch):
    body = _create(client)
    item_id = body["itemId"]
    mock_counter = Mock()
    monkeypatch.setattr(routes, "_apps_runtime_executions_counter", mock_counter)

    client.get(f"/configs/by-item/{item_id}")
    mock_counter.add.assert_not_called()

    response = client.get(f"/configs/by-item/{item_id}", params={"mode": "runtime"})
    assert response.status_code == 200
    mock_counter.add.assert_called_once_with(1)
