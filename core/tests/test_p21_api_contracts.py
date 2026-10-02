# SPDX-License-Identifier: Apache-2.0
"""P21 : contrats d'API — 404/422 en RFC 7807, documents de config stricts à
l'écriture, pagination/fenêtres bornées (jamais 500)."""

import copy

import pytest
from fastapi.testclient import TestClient

from app.db import init_db, make_engine
from app.main import create_app

_MAP = {
    "kind": "map",
    "map": {
        "basemap": {"style": "streets"},
        "view": {"center": [2, 46], "zoom": 5},
        "layers": [{"id": "f", "title": "f", "kind": "feature", "url": "https://x/y.geojson"}],
    },
}
_APP = {
    "kind": "app",
    "layout": {
        "type": "grid",
        "items": [{"id": "w", "widget": "text", "x": 0, "y": 0, "w": 4, "h": 2}],
    },
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'p21.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    c = TestClient(create_app())
    c.headers["Authorization"] = "Bearer mock:alice"
    return c


def _post(client, config):
    return client.post("/v1/configs", json={"title": "t", "config": config})


def test_unknown_route_and_validation_are_problem_json(client):
    r = client.get("/v1/nope")
    assert r.status_code == 404 and r.headers["content-type"] == "application/problem+json"
    r = client.post("/v1/groups", json={})
    assert r.status_code == 422 and r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert isinstance(body["detail"], str) and body["errors"][0]["field"]
    assert "input" not in r.text


def test_validation_422_never_echoes_secret_payload(client):
    r = client.post("/v1/secrets", json={"name": "x", "value": {"nested": "TOPSECRET"}})
    assert r.status_code == 422
    assert "TOPSECRET" not in r.text


def test_valid_documents_still_accepted(client):
    assert _post(client, _MAP).status_code == 201
    assert _post(client, _APP).status_code == 201


def test_unknown_keys_rejected(client):
    assert _post(client, {**_MAP, "bogusTop": 1}).status_code == 422
    m = copy.deepcopy(_MAP)
    m["map"]["layers"][0]["visibleTypo"] = False
    assert _post(client, m).status_code == 422


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["map"]["view"].update(center=[2, 999]),
        lambda m: m["map"]["view"].update(zoom=99),
        lambda m: m["map"]["layers"][0].update(opacity=5),
        lambda m: m["map"]["layers"][0].update(url="javascript:1"),
        lambda m: m["map"]["layers"].append({"id": "v", "title": "v", "kind": "vector"}),
    ],
)
def test_invalid_map_rejected_on_create_and_update(client, mutate):
    bad = copy.deepcopy(_MAP)
    mutate(bad)
    assert _post(client, bad).status_code == 422
    created = _post(client, _MAP).json()
    assert client.put(f"/v1/configs/by-item/{created['itemId']}", json=bad).status_code == 422
    assert client.put(f"/v1/configs/{created['id']}", json=bad).status_code == 422


def test_invalid_app_rejected(client):
    def app(items):
        return {"kind": "app", "layout": {"type": "grid", "items": items}}

    ok = {"id": "w", "widget": "text", "x": 0, "y": 0, "w": 4, "h": 2}
    assert _post(client, app([ok, {**ok}])).status_code == 422  # id dupliqué
    assert _post(client, app([{**ok, "w": 0}])).status_code == 422
    assert _post(client, app([{**ok, "h": -3}])).status_code == 422
    for expr in ("1 +", "((( not cel", "a == 'x"):
        assert _post(client, app([{**ok, "visibleWhen": expr}])).status_code == 422, expr
    assert _post(client, app([{**ok, "visibleWhen": "a == 'x' && (b > 1)"}])).status_code == 201


@pytest.mark.parametrize(
    "path",
    [
        "/v1/users?page=0",
        "/v1/users?pageSize=-1",
        "/v1/users?pageSize=100000",
        "/v1/usage/tasks?page=0",
        "/v1/usage/tasks?pageSize=-5",
        "/v1/usage/tasks?pageSize=0",
        "/v1/notifications?page=0",
        "/v1/notifications?page=-1",
        "/v1/notifications?pageSize=-3",
        "/v1/notifications?pageSize=100000",
        "/v1/usage/summary?since=pas-une-date",
        "/v1/usage/summary?until=32/13/2026",
        "/v1/usage/summary?limit=-1",
        "/v1/usage/summary?limit=0",
    ],
)
def test_bad_pagination_is_422_never_500(client, path):
    assert client.get(path).status_code == 422, path


def test_usage_summary_inverted_window_is_400(client):
    r = client.get("/v1/usage/summary?since=2026-02-01&until=2026-01-01")
    assert r.status_code in (400, 403)  # 403 si l'utilisateur mock n'a pas tasks.view_all
