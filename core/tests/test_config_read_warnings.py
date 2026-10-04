# SPDX-License-Identifier: Apache-2.0
"""REV-278/305 : une config stockée devenue invalide reste lisible, avec des
avertissements ; la réécriture du même document reste refusée."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.attributes import flag_modified

from app.configs.models import ConfigRevision
from app.db import init_db, make_engine, make_session_factory
from app.main import create_app

_APP = {
    "kind": "app",
    "layout": {
        "type": "grid",
        "items": [
            {"id": "a", "widget": "text", "x": 0, "y": 0, "w": 4, "h": 2},
            {"id": "b", "widget": "text", "x": 4, "y": 0, "w": 4, "h": 2},
        ],
    },
    "messages": [{"id": "m", "event": "click", "from": "a", "to": "b", "action": "setProp"}],
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'w.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    c = TestClient(create_app())
    c.headers["Authorization"] = "Bearer mock:alice"
    return c


def _alter(config_id, mutate):
    with make_session_factory(make_engine(os.environ["DATABASE_URL"]))() as s:
        rev = s.query(ConfigRevision).filter_by(config_id=config_id).one()
        data = rev.data
        mutate(data)
        rev.data = data
        flag_modified(rev, "data")
        s.commit()


def test_stored_config_failing_validation_is_readable_with_warnings(client):
    created = client.post("/v1/configs", json={"title": "t", "config": _APP}).json()
    assert created["warnings"] == []
    item_id, cid = created["itemId"], created["id"]

    def mutate(d):
        d["messages"][0]["to"] = "ghost"
        d["layout"]["items"][1]["widget"] = "inexistant"
        d["layout"]["items"][0]["visibleWhen"] = "a ==("

    _alter(cid, mutate)
    for url in (f"/v1/configs/by-item/{item_id}", f"/v1/configs/{cid}"):
        r = client.get(url)
        assert r.status_code == 200
        w = " | ".join(r.json()["warnings"])
        assert "ghost" in w and "inexistant" in w and "visibleWhen" in w
    doc = client.get(f"/v1/configs/by-item/{item_id}").json()["config"]
    assert client.put(f"/v1/configs/by-item/{item_id}", json={"config": doc}).status_code == 422


def test_healthy_config_has_no_warnings(client):
    created = client.post("/v1/configs", json={"title": "t", "config": _APP}).json()
    r = client.get(f"/v1/configs/by-item/{created['itemId']}")
    assert r.json()["warnings"] == []
