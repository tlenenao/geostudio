import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app.configs import routes


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    stub = StubItemClient()

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[routes.get_item_client] = lambda: stub

    test_client = TestClient(app)
    test_client.stub = stub  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _config_body(widget: str = "map") -> dict:
    return {
        "kind": "app",
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    }


def _create(client, widget: str = "map") -> dict:
    response = client.post("/configs", json={
        "title": "My App", "owner": "alice", "config": _config_body(widget)
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_create_config_creates_item_and_returns_201(client):
    body = _create(client)
    assert body["version"] == 1
    assert body["itemId"].startswith("item-")
    assert client.stub.created[0]["title"] == "My App"


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
    assert client.post(
        f"/configs/{created['id']}/rollback", json={"version": 99}
    ).status_code == 404


def test_delete_config_removes_it_and_deletes_linked_item(client):
    created = _create(client)
    config_id = created["id"]
    item_id = created["itemId"]

    response = client.delete(f"/configs/{config_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.stub.deleted == [item_id]
    assert client.get(f"/configs/{config_id}").status_code == 404


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
    assert response.content == b""
    assert client.stub.deleted == [item_id]
    assert client.get(f"/configs/{created['id']}").status_code == 404


def test_delete_by_item_missing_returns_404(client):
    assert client.delete("/configs/by-item/nope").status_code == 404


def _map_config() -> dict:
    return {
        "kind": "map",
        "map": {
            "basemap": {"style": "https://demotiles.maplibre.org/style.json"},
            "view": {"center": [2.35, 48.85], "zoom": 5},
            "layers": [
                {"id": "l1", "title": "Communes", "visible": True,
                 "kind": "vector", "tilesUrl": "https://martin/communes/{z}/{x}/{y}",
                 "sourceLayer": "communes"},
            ],
        },
    }


def test_map_config_round_trips_through_create_and_get(client):
    response = client.post(
        "/configs",
        json={"title": "Ma carte", "owner": "alice", "config": _map_config()},
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
        json={"title": "Ma carte", "owner": "alice", "config": _map_config()},
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
            "owner": "alice",
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
                    {"id": "a", "title": "A", "visible": True, "kind": "feature",
                     "url": "https://fs/a"}
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
        json={"kind": "map", "map": {
            "basemap": {"style": "s"}, "view": {"center": [0, 0], "zoom": 1}, "layers": []}},
    )
    assert resp.status_code == 404
