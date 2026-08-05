# SPDX-License-Identifier: Apache-2.0
"""run_analytics_query, source "arcgis" (SP-14l) — mirrors POST
/datasets/{id}/arcgis/aggregate: same live_query translate/fetch/aggregate
path, same bucket/split/bins rejection (no server-side equivalent in the
ArcGIS statistics API). get_arcgis_http_client is called as a plain
function inside the MCP tool body (no FastAPI Depends there), so tests
monkeypatch app.harvest.routes directly instead of using
app.dependency_overrides."""
import httpx
import pytest

from app.harvest import live_query, repository as harvest_repo, routes as harvest_routes
from app.items import repository as items_repo
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


@pytest.fixture(autouse=True)
def _clear_live_query_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def _register_arcgis_layer(app_client, *, owner=None):
    with app_client.session_factory() as session:
        layer_owner = owner or app_client.mock_user
        source = harvest_repo.create_source(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id,
            resource_type="external", title="Bâtiments",
        )
        if layer_owner is app_client.mock_user:
            items_repo.set_is_public(
                session, tenant_id=app_client.tenant.id, item_id=layer_item.id, is_public=True,
            )
        harvest_repo.create_record(
            session, tenant_id=app_client.tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url=SERVICE, layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def _register_dataset_item_for_arcgis_layer(app_client, arcgis_item_id):
    """Builds the dataset item/config directly (bypassing create_dataset's
    own validation), so a test can simulate a dataset that references an
    arcgis layer the caller can no longer read — create_dataset itself
    would refuse to create such a dataset in the first place (Task 1),
    so this is the only way to exercise run_analytics_query's own,
    independent re-check of layer readability."""
    with app_client.session_factory() as session:
        from app.configs import repository as configs_repo
        from app.configs.schemas import BuilderConfig, DatasetPayload
        item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=app_client.mock_user.id,
            resource_type="dataset", title="Bâtiments (live)",
        )
        config = BuilderConfig(
            version=1, kind="dataset",
            dataset=DatasetPayload(source="arcgis", arcgisItemId=arcgis_item_id, columns={}),
        )
        configs_repo.create_config(session, config, item_id=item.id, tenant_id=app_client.tenant.id)
        session.commit()
        return item.id


def test_run_analytics_query_arcgis_source_groupby_and_measure(app_client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [
            {"attributes": {"commune": "Metz", "m0": 3}},
            {"attributes": {"commune": "Nancy", "m0": 7}},
        ]})
    monkeypatch.setattr(
        harvest_routes, "get_arcgis_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        dataset_item_id = _register_dataset_item_for_arcgis_layer(app_client, arcgis_item_id)
        result = call_tool(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "commune", "agg": "count"},
        })

    assert result["categoryKey"] == "commune"
    assert result["rows"] == [{"commune": "Metz", "value": 3}, {"commune": "Nancy", "value": 7}]


def test_run_analytics_query_arcgis_source_rejects_bucket(app_client, monkeypatch):
    monkeypatch.setattr(
        harvest_routes, "get_arcgis_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []}))),
    )
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        dataset_item_id = _register_dataset_item_for_arcgis_layer(app_client, arcgis_item_id)
        error_text = call_tool_expecting_error(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "annee", "bucket": "month"},
        })
    assert "bucket/split/bins" in error_text


def test_run_analytics_query_arcgis_layer_unreadable_errors(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-raq-sub",
            username="otherowner-raq", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client, owner=other_owner)
        dataset_item_id = _register_dataset_item_for_arcgis_layer(app_client, arcgis_item_id)
        error_text = call_tool_expecting_error(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "commune"},
        })
    assert "not found" in error_text
