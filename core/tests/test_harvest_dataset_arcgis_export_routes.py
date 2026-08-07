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
