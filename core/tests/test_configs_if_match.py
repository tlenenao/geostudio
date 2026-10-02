# SPDX-License-Identifier: Apache-2.0
"""P09.04 (j04-008, t02-002) : PUT /configs avec `If-Match: <version lue>`
refuse en 412 une sauvegarde issue d'une version périmée ; sans l'en-tête,
comportement historique (dernier écrivain gagne) inchangé."""

import pytest
from fastapi.testclient import TestClient

from app.db import init_db, make_engine
from app.main import create_app

_MAP = {
    "kind": "map",
    "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'if_match.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    c = TestClient(create_app())
    c.headers["Authorization"] = "Bearer mock:alice"
    return c


@pytest.mark.parametrize("route", ["by-item", "by-id"])
def test_stale_if_match_is_refused_with_412(client, route):
    created = client.post("/v1/configs", json={"title": "Carte", "config": _MAP}).json()
    key = created["itemId"] if route == "by-item" else created["id"]
    url = f"/v1/configs/by-item/{key}" if route == "by-item" else f"/v1/configs/{key}"
    assert created["version"] == 1

    ok = client.put(url, json=_MAP, headers={"If-Match": '"1"'})
    assert ok.status_code == 200 and ok.json()["version"] == 2

    stale = client.put(url, json=_MAP, headers={"If-Match": '"1"'})
    assert stale.status_code == 412
    assert "version 2" in stale.json()["detail"]
    # rien n'a été écrit par le refus :
    assert client.get(url).json()["version"] == 2

    # sans en-tête (clients historiques) ou avec la version courante : accepté
    assert client.put(url, json=_MAP).status_code == 200
    assert client.put(url, json=_MAP, headers={"If-Match": "3"}).status_code == 200
    assert client.put(url, json=_MAP, headers={"If-Match": "3"}).status_code == 412


def test_invalid_if_match_is_a_400(client):
    created = client.post("/v1/configs", json={"title": "Carte", "config": _MAP}).json()
    r = client.put(f"/v1/configs/{created['id']}", json=_MAP, headers={"If-Match": "abc"})
    assert r.status_code == 400


def test_oversized_config_body_is_refused_before_being_read(client):
    # P09.07 (t02-001) : plafond de corps sur l'API JSON des configs.
    big = {"title": "x" * (6 * 1024 * 1024), "config": _MAP}
    assert client.post("/v1/configs", json=big).status_code == 413
    created = client.post("/v1/configs", json={"title": "Carte", "config": _MAP}).json()
    assert client.put(f"/v1/configs/{created['id']}", json=big).status_code == 413
    # corps chunked (sans Content-Length) : refusé, sinon le plafond se contourne
    chunked = client.post("/v1/configs", content=iter([b'{"title":"x"}']))
    assert chunked.status_code == 411
