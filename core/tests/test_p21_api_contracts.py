# SPDX-License-Identifier: Apache-2.0
"""P21 : contrats d'API — 404/422 en RFC 7807, documents de config stricts à
l'écriture, pagination/fenêtres bornées (jamais 500)."""

import copy
import os

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


def test_app_messages_must_target_existing_widgets_or_variables(client):
    """REV-278c : un câblage vers un widget/une variable inexistants est refusé."""
    items = [
        {"id": "btn", "widget": "button", "x": 0, "y": 0, "w": 2, "h": 1},
        {"id": "map", "widget": "map", "x": 2, "y": 0, "w": 4, "h": 4},
    ]

    def app(messages, variables=()):
        return {
            "kind": "app",
            "layout": {"type": "grid", "items": items},
            "messages": messages,
            "variables": list(variables),
        }

    msg = {"from": "btn", "event": "clicked", "to": "map", "action": "flyTo"}
    assert _post(client, app([msg])).status_code == 201
    r = _post(client, app([{**msg, "to": "ghost"}]))
    assert r.status_code == 422 and "ghost" in r.json()["detail"]
    r = _post(client, app([{**msg, "from": "nobody"}]))
    assert r.status_code == 422 and "nobody" in r.json()["detail"]
    var = {"id": "v1", "name": "Ville"}
    to_var = {**msg, "action": "set"}
    assert _post(client, app([{**to_var, "to": "var:v1"}], [var])).status_code == 201
    assert _post(client, app([{**to_var, "to": "var:v2"}], [var])).status_code == 422


def test_app_messages_accept_nested_widgets_and_page_on_enter(client):
    nested = {"id": "inner", "widget": "text", "x": 0, "y": 0, "w": 2, "h": 1}
    modal = {
        "id": "dlg",
        "widget": "modal",
        "x": 0,
        "y": 0,
        "w": 2,
        "h": 1,
        "props": {"title": "M", "items": [nested]},
    }
    page = {
        "id": "p1",
        "name": "P1",
        "layout": {"type": "grid", "items": [modal]},
        "onEnter": [{"from": "p1", "event": "enter", "to": "dlg", "action": "open"}],
    }
    config = {
        "kind": "app",
        "layout": {"type": "grid", "items": []},
        "pages": [page],
        "messages": [{"from": "inner", "event": "clicked", "to": "dlg", "action": "close"}],
    }
    assert _post(client, config).status_code == 201
    bad = copy.deepcopy(config)
    bad["pages"][0]["onEnter"][0]["to"] = "nowhere"
    assert _post(client, bad).status_code == 422


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


def test_stored_config_with_unknown_key_stays_readable(client):
    """Le rejet des clés inconnues est une règle d'ÉCRITURE : une config déjà
    stockée avec une clé retirée/ajoutée depuis doit rester lisible (GET,
    rollback, balayages cron)."""
    from sqlalchemy.orm.attributes import flag_modified

    from app.configs import repository as repo
    from app.configs.models import ConfigRevision
    from app.db import make_session_factory

    created = _post(client, _MAP).json()
    with make_session_factory(make_engine(os.environ["DATABASE_URL"]))() as s:
        rev = s.query(ConfigRevision).filter_by(config_id=created["id"]).one()
        rev.data = {**rev.data, "legacyTop": 1}
        rev.data["map"]["layers"][0]["legacyKey"] = True
        flag_modified(rev, "data")
        s.commit()
        assert [c for _, _, c in repo.list_configs_by_kind(s, "map")]
    assert client.get(f"/v1/configs/by-item/{created['itemId']}").status_code == 200
    assert client.get(f"/v1/configs/{created['id']}").status_code == 200
    assert _post(client, {**_MAP, "legacyTop": 1}).status_code == 422  # écriture toujours stricte
