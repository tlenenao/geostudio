# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy BAN authentifié, borné, erreurs RFC 7807."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import init_db, make_engine
from app.geocoding.provider import BanGeocoder, get_geocoder
from app.main import create_app

BAN_ANSWER = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [2.0628, 49.0316]},
            "properties": {"label": "1 Rue de Pontoise 95000 Cergy", "score": 0.9},
        }
    ],
}


@pytest.fixture
def app_and_client(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'geocode.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    app = create_app()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return app, client


def _fake_ban(app, handler):
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    app.dependency_overrides[get_geocoder] = lambda: BanGeocoder(
        "https://data.geopf.fr/geocodage/search",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(recording)),
    )
    return seen


def test_returns_label_and_coordinates(app_and_client):
    app, client = app_and_client
    seen = _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    r = client.get("/v1/geocode", params={"q": "1 rue de pontoise cergy", "limit": 3})
    assert r.status_code == 200
    assert r.json() == {
        "results": [{"label": "1 Rue de Pontoise 95000 Cergy", "lon": 2.0628, "lat": 49.0316}]
    }
    assert seen[0].url.params["q"] == "1 rue de pontoise cergy"
    assert seen[0].url.params["limit"] == "3"


def test_requires_authentication(app_and_client):
    app, client = app_and_client
    _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    del client.headers["Authorization"]
    assert client.get("/v1/geocode", params={"q": "cergy"}).status_code == 401


@pytest.mark.parametrize(
    "params",
    [{"q": "ab"}, {"q": "x" * 201}, {"q": "cergy", "limit": 0}, {"q": "cergy", "limit": 11}],
)
def test_rejects_out_of_bounds_parameters(app_and_client, params):
    app, client = app_and_client
    _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    assert client.get("/v1/geocode", params=params).status_code == 422


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, content=b"pas du json"),
        lambda r: httpx.Response(200, json={"features": [{"geometry": None}]}),
    ],
)
def test_upstream_failure_is_a_502_problem(app_and_client, handler):
    app, client = app_and_client
    _fake_ban(app, handler)
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 502
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["detail"] == "Le service de géocodage est indisponible."


def test_empty_url_disables_geocoding(app_and_client, monkeypatch):
    _, client = app_and_client
    monkeypatch.setenv("CORE_GEOCODING_URL", "")
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Géocodage désactivé sur cette instance."


def test_unauthenticated_with_empty_url_is_401_not_503(app_and_client, monkeypatch):
    _, client = app_and_client
    monkeypatch.setenv("CORE_GEOCODING_URL", "")
    del client.headers["Authorization"]
    assert client.get("/v1/geocode", params={"q": "cergy"}).status_code == 401


def test_egress_guard_failure_is_a_502(app_and_client, monkeypatch):
    _, client = app_and_client
    monkeypatch.setenv("CORE_GEOCODING_URL", "http://127.0.0.1:1/search")

    # Prouve que c'est la garde (et non un échec de connexion) qui répond : si le
    # client par défaut n'était pas gardé, la requête atteindrait ce transport.
    def _reached(self, request):
        raise AssertionError("requête sortie sans passer par la garde d'egress")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _reached)
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 502
    assert r.json()["detail"] == "Le service de géocodage est indisponible."


def test_default_client_factory_is_the_guarded_one():
    from app.geocoding.egress import build_guarded_client

    assert BanGeocoder("https://x")._client_factory is build_guarded_client
