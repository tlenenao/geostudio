# SPDX-License-Identifier: Apache-2.0
"""explain_dataset, source "arcgis" (SP-14l) — a live GET {external_url}
?f=json through the egress-guarded client (same client seam as
run_analytics_query's arcgis path), extracting ArcGIS's standard layer
`fields: [{name, type, alias}]`."""

import httpx

from app.harvest import repository as harvest_repo
from app.harvest import routes as harvest_routes
from app.items import repository as items_repo
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


def _register_arcgis_layer(app_client):
    with app_client.session_factory() as session:
        source = harvest_repo.create_source(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference",
            enabled=True,
            interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="external",
            title="Bâtiments",
        )
        harvest_repo.create_record(
            session,
            tenant_id=app_client.tenant.id,
            source_id=source.id,
            external_id="layer-0",
            item_id=layer_item.id,
            collection_id=None,
            content_hash=None,
            external_url=SERVICE,
            layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def test_explain_dataset_arcgis_source_returns_fields_from_live_layer_metadata(
    app_client, monkeypatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{SERVICE}?f=json"
        return httpx.Response(
            200,
            json={
                "name": "Bâtiments",
                "fields": [
                    {"name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID"},
                    {"name": "commune", "type": "esriFieldTypeString", "alias": "Commune"},
                ],
            },
        )

    monkeypatch.setattr(
        harvest_routes,
        "get_arcgis_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        create_result = call_tool(
            app_client,
            "create_dataset",
            {
                "title": "Bâtiments (live)",
                "source": "arcgis",
                "arcgisItemId": arcgis_item_id,
            },
        )
        result = call_tool(app_client, "explain_dataset", {"datasetId": create_result["pk"]})

    assert result["source"] == "arcgis"
    assert {"name": "commune", "type": "esriFieldTypeString"} in result["fields"]
