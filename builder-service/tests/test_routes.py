import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app import routes


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

    app.dependency_overrides[routes.get_session] = override_session
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
