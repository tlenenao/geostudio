# SPDX-License-Identifier: Apache-2.0
"""ARC-34 (ADR 0025) : client Valhalla + routes /v1/routing, contre un faux Valhalla
(httpx.MockTransport) — aucun vrai service requis."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.models import AuditLog
from app.db import init_db, make_engine
from app.main import create_app
from app.routing import client as rc
from app.routing.client import Valhalla

TULLE = {"lon": 1.77, "lat": 45.26}
BRIVE = {"lon": 1.53, "lat": 45.16}


def _encode6(coords):  # [[lon, lat]] -> polyline6 (pour fabriquer la réponse du faux Valhalla)
    out, plat, plon = [], 0, 0
    for lon, lat in coords:
        for v, p in ((round(lat * 1e6), plat), (round(lon * 1e6), plon)):
            d = v - p
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plon = round(lat * 1e6), round(lon * 1e6)
    return "".join(out)


SHAPE = [[1.77, 45.26], [1.65, 45.2], [1.53, 45.16]]
POLY = {
    "type": "Polygon",
    "coordinates": [[[1.7, 45.2], [1.8, 45.2], [1.8, 45.3], [1.7, 45.2]]],
}


def fake_valhalla(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        if request.url.path == "/route":
            if body["locations"][0]["lon"] == 0:
                return httpx.Response(400, json={"error_code": 171, "error": "No suitable edges"})
            return httpx.Response(
                200,
                json={
                    "trip": {
                        "summary": {"length": 25.4, "time": 1800.0},
                        "legs": [
                            {
                                "shape": _encode6(SHAPE),
                                "summary": {"length": 25.4, "time": 1800.0},
                                "maneuvers": [
                                    {"instruction": "Tournez.", "length": 1.0, "time": 60}
                                ],
                            }
                        ],
                    }
                },
            )
        if request.url.path == "/isochrone":
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": POLY,
                            "properties": {"contour": c["time"], "metric": "time"},
                        }
                        for c in body["contours"]
                    ],
                },
            )
        if request.url.path == "/sources_to_targets":
            return httpx.Response(
                200,
                json={
                    "sources_to_targets": [
                        [{"distance": 1.5, "time": 90} for _ in body["targets"]]
                        for _ in body["sources"]
                    ]
                },
            )
        return httpx.Response(404)

    return handler


def _valhalla(handler) -> Valhalla:
    return Valhalla(
        "http://valhalla:8002", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


@pytest.fixture
def api(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'routing.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ROUTING_URL", "http://valhalla:8002")
    engine = make_engine(url)
    init_db(engine)
    seen: list = []
    monkeypatch.setattr("app.routing.routes.get_routing", lambda: _valhalla(fake_valhalla(seen)))
    monkeypatch.setattr(rc, "rate_window", rc._Window())
    monkeypatch.setattr("app.routing.routes.rate_window", rc.rate_window)
    client = TestClient(create_app())
    client.headers["Authorization"] = "Bearer mock:alice"
    client.seen, client.engine = seen, engine  # type: ignore[attr-defined]
    return client


def test_route_decodes_geometry_and_summary(api):
    r = api.post("/v1/routing/route", json={"points": [TULLE, BRIVE], "costing": "bicycle"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["distance_km"] == 25.4 and body["duration_s"] == 1800.0
    assert body["geometry"]["coordinates"] == SHAPE
    assert body["legs"][0]["maneuvers"][0]["instruction"] == "Tournez."
    assert api.seen[0][1]["costing"] == "bicycle"


def test_isochrone_returns_polygons_with_minutes(api):
    r = api.post("/v1/routing/isochrone", json={"origin": TULLE, "minutes": [10, 5]})
    assert r.status_code == 200, r.text
    feats = r.json()["features"]
    assert [f["properties"]["contour_minutes"] for f in feats] == [5, 10]
    assert feats[0]["geometry"]["type"] == "Polygon"


def test_service_area_tags_origin_index(api):
    r = api.post("/v1/routing/service-area", json={"origins": [TULLE, BRIVE], "minutes": [10]})
    assert r.status_code == 200, r.text
    assert [f["properties"]["origin_index"] for f in r.json()["features"]] == [0, 1]


def test_matrix_shape(api):
    r = api.post("/v1/routing/matrix", json={"sources": [TULLE], "targets": [BRIVE, TULLE]})
    assert r.status_code == 200, r.text
    assert r.json()["matrix"] == [[{"distance_km": 1.5, "duration_s": 90}] * 2]


@pytest.mark.parametrize(
    "path,body",
    [
        ("route", {"points": [TULLE]}),
        ("route", {"points": [TULLE] * 21}),
        ("route", {"points": [TULLE, BRIVE], "costing": "tank"}),
        ("route", {"points": [{"lon": 999, "lat": 0}, BRIVE]}),
        ("isochrone", {"origin": TULLE, "minutes": [61]}),
        ("isochrone", {"origin": TULLE, "minutes": [1, 2, 3, 4, 5]}),
        ("matrix", {"sources": [TULLE] * 40, "targets": [BRIVE] * 30}),  # 1200 cellules
    ],
)
def test_caps_are_422(api, path, body):
    assert api.post(f"/v1/routing/{path}", json=body).status_code == 422
    assert api.seen == []


def test_no_route_is_a_422_with_upstream_message(api):
    r = api.post("/v1/routing/route", json={"points": [{"lon": 0, "lat": 0}, BRIVE]})
    assert r.status_code == 422
    assert "No suitable edges" in r.json()["detail"]


def test_service_not_configured_is_503_problem(api, monkeypatch):
    monkeypatch.setattr("app.routing.routes.get_routing", rc.get_routing)
    monkeypatch.setenv("CORE_ROUTING_URL", "")
    r = api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]})
    assert r.status_code == 503
    assert r.headers["content-type"] == "application/problem+json"
    assert "désactivé" in r.json()["detail"]


def test_unreachable_or_broken_upstream_is_503(api, monkeypatch):
    for handler in (
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, content=b"pas du json"),
        lambda r: httpx.Response(200, json={"trip": {}}),
    ):
        monkeypatch.setattr("app.routing.routes.get_routing", lambda h=handler: _valhalla(h))
        r = api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]})
        assert r.status_code == 503
        assert r.json()["detail"] == "Le service de routage est indisponible."


def test_requires_authentication(api):
    del api.headers["Authorization"]
    assert api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]}).status_code == 401


def test_101st_call_in_a_minute_is_429(api):
    for _ in range(100):
        assert api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]}).status_code == 200
    r = api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]})
    assert r.status_code == 429
    assert len(api.seen) == 100


def test_every_call_is_audited_even_when_service_is_down(api, monkeypatch):
    api.post("/v1/routing/route", json={"points": [TULLE, BRIVE]})
    monkeypatch.setattr(
        "app.routing.routes.get_routing", lambda: _valhalla(lambda r: httpx.Response(500))
    )
    api.post("/v1/routing/isochrone", json={"origin": TULLE, "minutes": [10]})
    from sqlalchemy.orm import Session

    with Session(api.engine) as s:
        rows = [r for r in s.scalars(select(AuditLog)) if r.action.startswith("routing.")]
    assert [(r.action, r.payload) for r in rows] == [
        ("routing.route", {"costing": "auto", "points": 2}),
        ("routing.isochrone", {"costing": "auto", "contours": 1}),
    ]
    assert "45.26" not in json.dumps([r.payload for r in rows])  # pas de coordonnées dans l'audit


# --- garde d'egress ---------------------------------------------------------------------


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("CORE_ROUTING_URL", "http://10.1.2.3:8002")


def test_egress_allows_the_configured_private_host(configured):
    assert str(rc.assert_egress_allowed("http://10.1.2.3:8002/route")) == "10.1.2.3"


@pytest.mark.parametrize(
    "url",
    [
        "http://10.9.9.9/route",
        "http://169.254.169.254/route",
        "ftp://10.1.2.3/x",
        "http://evil.test/",
    ],
)
def test_egress_refuses_other_hosts_and_schemes(configured, url):
    with pytest.raises(rc._EgressBlocked):
        rc.assert_egress_allowed(url)


def test_egress_refuses_metadata_even_when_configured(monkeypatch):
    monkeypatch.setenv("CORE_ROUTING_URL", "http://169.254.169.254")
    with pytest.raises(rc._EgressBlocked):
        rc.assert_egress_allowed("http://169.254.169.254/route")


def test_default_client_goes_through_the_guard(monkeypatch):
    monkeypatch.setenv("CORE_ROUTING_URL", "http://169.254.169.254")

    def _reached(self, request):
        raise AssertionError("requête sortie sans passer par la garde d'egress")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _reached)
    with pytest.raises(rc.RoutingUnavailable):
        Valhalla("http://169.254.169.254").route([TULLE, BRIVE])


def test_polyline_roundtrip():
    assert rc.decode_polyline6(_encode6(SHAPE)) == SHAPE
