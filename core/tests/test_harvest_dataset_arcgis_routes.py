# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import live_query
from app.harvest import repository as harvest_repo
from app.harvest import routes as harvest_routes
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
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email="a@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        source = harvest_repo.create_source(
            s,
            tenant_id=tenant.id,
            owner_id=alice.id,
            type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference",
            enabled=True,
            interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=alice.id,
            resource_type="external",
            title="Bâtiments",
        )
        harvest_repo.create_record(
            s,
            tenant_id=tenant.id,
            source_id=source.id,
            external_id="layer-0",
            item_id=layer_item.id,
            collection_id=None,
            content_hash=None,
            external_url=SERVICE,
            layer_kind="feature",
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
    test_client.alice_id = alice.id  # type: ignore[attr-defined]
    test_client.tenant_id = tenant.id  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_dataset(client, arcgis_item_id: str) -> str:
    res = client.post(
        "/v1/configs",
        json={
            "title": "Bâtiments (live)",
            "config": {
                "version": 1,
                "kind": "dataset",
                "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["itemId"]


def test_get_items_proxies_to_arcgis_and_reshapes_response(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(f"{SERVICE}/query")
        assert "where=1%3D1" in str(request.url) or "where=1=1" in str(request.url)
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "id": 1, "properties": {"nom": "X"}, "geometry": None}
                ],
            },
        )

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(
        handler
    )
    resp = client.get(f"/v1/datasets/{dataset_item_id}/arcgis/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == [
        {"type": "Feature", "id": 1, "properties": {"nom": "X"}, "geometry": None}
    ]
    assert body["numberReturned"] == 1
    assert body["numberMatched"] == 1


def test_get_items_forwards_filters_and_bbox(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"features": []})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(
        handler
    )
    resp = client.get(
        f"/v1/datasets/{dataset_item_id}/arcgis/items",
        params={"statut": "actif", "bbox": "1,2,3,4", "limit": "5", "offset": "0"},
    )
    assert resp.status_code == 200
    assert "statut" in seen["url"]
    assert "geometryType=esriGeometryEnvelope" in seen["url"]
    assert "resultRecordCount=5" in seen["url"]


def test_get_items_unknown_dataset_item_404s(client):
    resp = client.get("/v1/datasets/no-such-item/arcgis/items")
    assert resp.status_code == 404


def test_get_items_egress_blocked_returns_502(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def raising_client():
        from app.harvest.egress import EgressBlockedError

        class _RaisingClient:
            def get(self, *args, **kwargs):
                raise EgressBlockedError("cible interne bloquée")

            def close(self):
                pass

        return _RaisingClient()

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = raising_client
    resp = client.get(f"/v1/datasets/{dataset_item_id}/arcgis/items")
    assert resp.status_code == 502


def test_post_aggregate_no_groupby_count(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "outStatistics" in str(request.url)
        return httpx.Response(200, json={"features": [{"attributes": {"m0": 12}}]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(
        handler
    )
    resp = client.post(f"/v1/datasets/{dataset_item_id}/arcgis/aggregate", json={"agg": "count"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoryKey"] == "group"
    assert body["rows"] == [{"group": "Total", "value": 12}]


def test_post_aggregate_groupby_and_measure(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {"attributes": {"commune": "Metz", "m0": 3}},
                    {"attributes": {"commune": "Nancy", "m0": 7}},
                ]
            },
        )

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(
        handler
    )
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "groupBy": "commune",
            "agg": "count",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoryKey"] == "commune"
    assert body["rows"] == [{"commune": "Metz", "value": 3}, {"commune": "Nancy", "value": 7}]


def test_get_items_invalid_filter_field_name_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.get(
        f"/v1/datasets/{dataset_item_id}/arcgis/items",
        params={"1) OR (1=1--": "x"},
    )
    assert resp.status_code == 400


def test_post_aggregate_invalid_filter_field_name_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "agg": "count",
            "filters": {"1) OR (1=1--": "x"},
        },
    )
    assert resp.status_code == 400


def test_post_aggregate_invalid_groupby_field_name_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "agg": "count",
            "groupBy": "1) OR (1=1--",
        },
    )
    assert resp.status_code == 400


def test_post_aggregate_bucket_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "groupBy": "annee",
            "bucket": "month",
        },
    )
    assert resp.status_code == 400


def test_post_aggregate_split_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "groupBy": "annee",
            "split": "commune",
        },
    )
    assert resp.status_code == 400


def test_post_aggregate_bins_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(
        f"/v1/datasets/{dataset_item_id}/arcgis/aggregate",
        json={
            "field": "population",
            "bins": 10,
        },
    )
    assert resp.status_code == 400


def test_get_items_on_collection_dataset_404s(client):
    # Seed a real, readable collection so the dataset actually gets created
    # (a collection-sourced dataset needs a valid collectionId to pass
    # validation — Task 1) — only then is the arcgis-route rejection real.
    from app.collections.models import Collection

    with client.session_factory() as s:
        s.add(
            Collection(
                id="parcs",
                tenant_id=client.tenant_id,
                owner_id=client.alice_id,
                table_name="parcs",
                title="Parcs",
                pk_column="id",
                is_public=True,
                editable=True,
            )
        )
        s.commit()

    res = client.post(
        "/v1/configs",
        json={
            "title": "Dataset collection",
            "config": {
                "version": 1,
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "parcs", "columns": {}},
            },
        },
    )
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    resp = client.get(f"/v1/datasets/{item_id}/arcgis/items")
    assert resp.status_code == 404
