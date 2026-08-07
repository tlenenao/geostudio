# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import live_query, routes as harvest_routes
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


@pytest.fixture(autouse=True)
def _clear_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="a@example.com", first_name="Alice", last_name="Doe",
        )
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=alice.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=alice.id, resource_type="external", title="Bâtiments",
        )
        harvest_repo.create_record(
            s, tenant_id=tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url=SERVICE, layer_kind="feature",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.layer_item_id = layer_item.id  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_dataset(client, arcgis_item_id: str) -> str:
    res = client.post("/configs", json={
        "title": "Bâtiments (live)",
        "config": {
            "version": 1, "kind": "dataset",
            "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
        },
    })
    assert res.status_code == 201, res.text
    return res.json()["itemId"]


def test_export_aggregate_csv_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "features": [{"attributes": {"region": "Nord", "m0": 3}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv",
                        json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Nord" in resp.text


def test_export_aggregate_rejects_unknown_format(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=pdf", json={"groupBy": "region"})
    assert resp.status_code == 400


def test_export_aggregate_writes_an_audit_log_row(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [{"attributes": {"region": "Nord", "m0": 3}}]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv", json={"groupBy": "region", "agg": "count"})
    with client.session_factory() as s:
        rows = s.query(AuditLog).filter_by(action="export.run").all()
    assert len(rows) == 1
    assert rows[0].payload == {"format": "csv", "mode": "aggregate"}


def test_export_items_geojson_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    body = resp.json()
    assert body["features"][0]["properties"]["nom"] == "X"


def test_export_items_gpkg_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"},
                          "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_stops_paginating_on_a_short_page(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    assert len(calls) == 1  # one page returned fewer rows than the page size — loop stops


def test_export_items_continues_past_a_full_page(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            # A full page (== the route's page size, _MAX_LIMIT=1000): the loop
            # must not stop here and must issue a second request with an
            # incremented offset.
            features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}] * 1000
        else:
            # Second page is short: the loop stops here.
            features = [{"type": "Feature", "properties": {"nom": "Y"}, "geometry": None}]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    assert len(calls) == 2  # a full first page forces a second real HTTP call
    assert "resultOffset=0" in calls[0]
    assert "resultOffset=1000" in calls[1]  # offset actually incremented by the page size
    body = resp.json()
    assert len(body["features"]) == 1001  # both pages' features were accumulated


def test_export_items_continues_past_a_clamped_short_page_when_exceeded_transfer_limit_is_set(client):
    # Regression (SP-16a final review, Important #4): a real ArcGIS service
    # clamps resultRecordCount to its own maxRecordCount (e.g. maxRecordCount=500
    # for our requested limit=1000). The returned page is then shorter than
    # `limit` even though more features remain — exceededTransferLimit=true is
    # the authoritative "there's more" signal (mirrors connectors/arcgis.py:139)
    # and must override the `len(page_features) < limit` heuristic.
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            # Clamped page: fewer rows than the requested limit, but the
            # service signals there is more to fetch.
            features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}] * 500
            return httpx.Response(200, json={
                "type": "FeatureCollection", "features": features, "exceededTransferLimit": True,
            })
        features = [{"type": "Feature", "properties": {"nom": "Y"}, "geometry": None}]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    assert len(calls) == 2  # a short-but-clamped first page still forces a second HTTP call
    body = resp.json()
    assert len(body["features"]) == 501  # both pages' features were accumulated, nothing lost


def test_export_items_caps_at_10000_entities(client, monkeypatch):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    monkeypatch.setattr(harvest_routes, "_EXPORT_ITEMS_CAP", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        # Always return a full page (limit=1000) so the loop keeps paginating
        # until the (monkeypatched) cap trips.
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}] * 1000,
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 413
