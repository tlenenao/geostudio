# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""ARC-03 : géocodage par lot + reverse (BAN simulée, jamais le réseau réel)."""

import time

import httpx
import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.geocoding.batch import _Pacer, geocode_batch
from app.geocoding.provider import BanGeocoder, GeocodeResult, NominatimGeocoder, get_geocoder
from tests.test_geocoding_routes import BAN_ANSWER, app_and_client  # noqa: F401
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)

URL = "https://data.geopf.fr/geocodage/search"


def _ban(handler):
    return BanGeocoder(
        URL, client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _handler(request: httpx.Request) -> httpx.Response:
    q = request.url.params.get("q", "")
    if "inconnue" in q:
        return httpx.Response(200, json={"features": []})
    if "panne" in q:
        return httpx.Response(500)
    return httpx.Response(200, json=BAN_ANSWER)


def test_batch_500_addresses_reports_not_found_quickly():
    addresses = [f"{i} rue inconnue" if i % 10 == 0 else f"{i} rue de pontoise" for i in range(500)]
    t0 = time.monotonic()
    rows = geocode_batch(_ban(_handler), addresses, per_second=1e6)
    assert time.monotonic() - t0 < 60
    assert [r.address for r in rows] == addresses  # ordre conservé
    assert sum(r.status == "non_trouvé" for r in rows) == 50
    assert sum(r.status == "trouvé" for r in rows) == 450
    assert rows[1].lon == 2.0628


def test_batch_row_error_does_not_lose_the_batch():
    rows = geocode_batch(_ban(_handler), ["panne ici", "1 rue de pontoise"], per_second=1e6)
    assert [r.status for r in rows] == ["erreur", "trouvé"]


def test_pacer_caps_rate_to_ban_ceiling():
    now, slept = [0.0], []

    def sleep(d):
        slept.append(d)
        now[0] += d

    p = _Pacer(50, clock=lambda: now[0], sleep=sleep)
    for _ in range(101):
        p.wait()
    assert now[0] == pytest.approx(2.0)  # 101 appels >= 2 s à 50 req/s


def test_batch_route(app_and_client):
    app, client = app_and_client
    app.dependency_overrides[get_geocoder] = lambda: _ban(_handler)
    r = client.post("/v1/geocode/batch", json={"addresses": ["1 rue x", "rue inconnue"]})
    assert r.status_code == 200
    body = r.json()
    assert (body["found"], body["not_found"], body["errors"]) == (1, 1, 0)
    assert body["results"][1]["status"] == "non_trouvé"


@pytest.mark.parametrize("addresses", [[], ["ok ok"] * 501, ["ab"], ["x" * 201]])
def test_batch_route_bounds(app_and_client, addresses):
    app, client = app_and_client
    app.dependency_overrides[get_geocoder] = lambda: _ban(_handler)
    assert client.post("/v1/geocode/batch", json={"addresses": addresses}).status_code == 422


def test_batch_route_all_upstream_down_is_502(app_and_client):
    app, client = app_and_client
    app.dependency_overrides[get_geocoder] = lambda: _ban(lambda r: httpx.Response(500))
    r = client.post("/v1/geocode/batch", json={"addresses": ["1 rue x"]})
    assert r.status_code == 502


def test_batch_requires_authentication(app_and_client):
    _, client = app_and_client
    del client.headers["Authorization"]
    assert client.post("/v1/geocode/batch", json={"addresses": ["1 rue x"]}).status_code == 401


def test_reverse_returns_address(app_and_client):
    app, client = app_and_client
    seen = []

    def h(request):
        seen.append(request)
        return httpx.Response(200, json=BAN_ANSWER)

    app.dependency_overrides[get_geocoder] = lambda: _ban(h)
    r = client.get("/v1/geocode/reverse", params={"lon": 2.0628, "lat": 49.0316})
    assert r.status_code == 200
    assert r.json()["result"]["label"] == "1 Rue de Pontoise 95000 Cergy"
    assert str(seen[0].url).startswith("https://data.geopf.fr/geocodage/reverse?")


def test_reverse_nothing_found_and_bounds(app_and_client):
    app, client = app_and_client
    app.dependency_overrides[get_geocoder] = lambda: _ban(
        lambda r: httpx.Response(200, json={"features": []})
    )
    assert client.get("/v1/geocode/reverse", params={"lon": 0, "lat": 0}).json() == {"result": None}
    assert client.get("/v1/geocode/reverse", params={"lon": 200, "lat": 0}).status_code == 422
    assert client.get("/v1/geocode/reverse", params={"lon": "nan", "lat": 0}).status_code == 422


def test_reverse_upstream_failure_is_502(app_and_client):
    app, client = app_and_client
    app.dependency_overrides[get_geocoder] = lambda: _ban(lambda r: httpx.Response(500))
    assert client.get("/v1/geocode/reverse", params={"lon": 1, "lat": 1}).status_code == 502


def test_nominatim_reverse():
    g = NominatimGeocoder(
        "https://nom.example/search",
        client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"display_name": "Tulle", "lon": "1.77", "lat": "45.26"}
                )
            )
        ),
    )
    result = g.reverse(1.77, 45.26)
    assert result is not None and result.label == "Tulle"


def test_rate_limit_group_covers_new_routes():
    from app.main import _EXPORT_PATH_RE
    from app.ratelimit.limiter import route_group

    assert route_group("/v1/geocode/batch", "POST", _EXPORT_PATH_RE) == "geocode"
    assert route_group("/v1/geocode/reverse", "GET", _EXPORT_PATH_RE) == "geocode"


class _Stub:
    def __init__(self, rows):
        self.rows = rows

    def search(self, q, limit):
        return self.rows.get(q, [])


def test_mcp_geocode_batch_is_audited(app_client, monkeypatch):
    stub = _Stub({"tulle": [GeocodeResult(label="Tulle", lon=1.77, lat=45.26)]})
    monkeypatch.setattr("app.mcp.tools.geocode.get_geocoder", lambda: stub)
    with app_client:
        out = call_tool(app_client, "geocode_batch", {"addresses": ["tulle", "nulle part"]})
    assert (out["found"], out["not_found"]) == (1, 1)
    assert out["results"][0]["label"] == "Tulle"
    with app_client.session_factory() as session:
        rows = [r for r in session.scalars(select(AuditLog)) if r.action == "mcp.tool_call"]
    assert [r.object_id for r in rows] == ["geocode_batch"]


@pytest.mark.parametrize("addresses", [[], ["ab"], ["ville"] * 501])
def test_mcp_geocode_batch_bounds(app_client, monkeypatch, addresses):
    monkeypatch.setattr("app.mcp.tools.geocode.get_geocoder", lambda: _Stub({}))
    with app_client:
        call_tool_expecting_error(app_client, "geocode_batch", {"addresses": addresses})


def test_pacer_is_global_across_batches(monkeypatch):
    # La cadence BAN (≤ 50 req/s/IP) vaut pour le process, pas pour chaque lot.
    from app.geocoding import batch

    now = [0.0]

    def sleep(d):
        now[0] += d

    monkeypatch.setattr(batch, "_PACER", _Pacer(50, clock=lambda: now[0], sleep=sleep))
    for _ in range(2):  # deux lots successifs, même pacer
        geocode_batch(_ban(_handler), ["1 rue de pontoise"] * 51)
    assert now[0] >= 101 / 50 - 1e-9  # 102 appels >= ~2 s, pas 1 s


def _blocking_geocoder():
    import threading

    started, release = threading.Event(), threading.Event()

    class Slow:
        def search(self, q, limit):
            started.set()
            release.wait(5)
            return []

    return Slow(), started, release


def test_second_concurrent_batch_is_refused():
    import threading

    from app.geocoding.batch import BatchBusy

    slow, started, release = _blocking_geocoder()
    t = threading.Thread(target=lambda: geocode_batch(slow, ["1 rue x"], per_second=1e6))
    t.start()
    try:
        assert started.wait(5)
        with pytest.raises(BatchBusy):
            geocode_batch(_ban(_handler), ["1 rue x"], per_second=1e6)
    finally:
        release.set()
        t.join()
    geocode_batch(_ban(_handler), ["1 rue x"], per_second=1e6)  # verrou relâché


def test_batch_route_busy_is_429(app_and_client):
    import threading

    app, client = app_and_client
    slow, started, release = _blocking_geocoder()
    t = threading.Thread(target=lambda: geocode_batch(slow, ["1 rue x"], per_second=1e6))
    t.start()
    try:
        assert started.wait(5)
        app.dependency_overrides[get_geocoder] = lambda: _ban(_handler)
        r = client.post("/v1/geocode/batch", json={"addresses": ["1 rue x"]})
        assert r.status_code == 429
    finally:
        release.set()
        t.join()
