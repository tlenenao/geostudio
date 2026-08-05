### Task 3: `explain_dataset` tool

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_explain_dataset.py` (new — source `collection`, needs real PostGIS)
- Test: `core/tests/test_mcp_tools_explain_dataset_arcgis.py` (new — source `arcgis`, SQLite)

**Interfaces:**
- Consumes: `_resolve_dataset_payload`, `_resolve_arcgis_external_url` (Task 2).
- Consumes: `create_dataset` (Task 1) to build fixtures in tests.
- Produces: MCP tool `explain_dataset(ctx, datasetId: str) -> dict` returning `{"title": str, "source": "collection"|"arcgis", "timeField": str|None, "reactsToExtent": bool, "columns": dict, "fields": list[{"name": str, "type": str}]}`.

- [ ] **Step 1: Write the failing tests (collection source)**

Create `core/tests/test_mcp_tools_explain_dataset.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""explain_dataset, source "collection" (SP-14l) — introspected field
name+type (via app.collections.schema_json.table_info_to_schema, the same
helper create_form_app already uses) plus author metadata as stored on the
DatasetPayload. No stats, no sampling (design §1 non-buts)."""
import pytest

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import app_client, _register_incidents_collection  # noqa: F401

pytestmark = pytest.mark.postgis


def test_explain_dataset_collection_source_returns_fields_and_metadata(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        create_result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
            "columns": {"titre": {"label": "Titre de l'incident", "description": None, "format": None}},
            "timeField": None, "reactsToExtent": True,
        })
        result = call_tool(app_client, "explain_dataset", {"datasetId": create_result["pk"]})

    assert result["title"] == "Incidents (dataset)"
    assert result["source"] == "collection"
    assert result["reactsToExtent"] is True
    assert result["columns"]["titre"]["label"] == "Titre de l'incident"
    field_names = {f["name"] for f in result["fields"]}
    assert "titre" in field_names


def test_explain_dataset_dataset_not_found_errors(app_client):
    with app_client:
        error_text = call_tool_expecting_error(app_client, "explain_dataset", {"datasetId": "does-not-exist"})
    assert "not found" in error_text
```

- [ ] **Step 2: Write the failing tests (arcgis source)**

Create `core/tests/test_mcp_tools_explain_dataset_arcgis.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""explain_dataset, source "arcgis" (SP-14l) — a live GET {external_url}
?f=json through the egress-guarded client (same client seam as
run_analytics_query's arcgis path), extracting ArcGIS's standard layer
`fields: [{name, type, alias}]`."""
import httpx
import pytest

from app.harvest import repository as harvest_repo, routes as harvest_routes
from app.items import repository as items_repo

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


def _register_arcgis_layer(app_client):
    with app_client.session_factory() as session:
        source = harvest_repo.create_source(
            session, tenant_id=app_client.tenant.id, owner_id=app_client.mock_user.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=app_client.mock_user.id,
            resource_type="external", title="Bâtiments",
        )
        harvest_repo.create_record(
            session, tenant_id=app_client.tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url=SERVICE, layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def test_explain_dataset_arcgis_source_returns_fields_from_live_layer_metadata(app_client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{SERVICE}?f=json"
        return httpx.Response(200, json={
            "name": "Bâtiments",
            "fields": [
                {"name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID"},
                {"name": "commune", "type": "esriFieldTypeString", "alias": "Commune"},
            ],
        })
    monkeypatch.setattr(
        harvest_routes, "get_arcgis_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        create_result = call_tool(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })
        result = call_tool(app_client, "explain_dataset", {"datasetId": create_result["pk"]})

    assert result["source"] == "arcgis"
    assert {"name": "commune", "type": "esriFieldTypeString"} in result["fields"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_explain_dataset.py tests/test_mcp_tools_explain_dataset_arcgis.py -v`
Expected: all FAIL — `explain_dataset` tool does not exist yet.

- [ ] **Step 4: Implement `explain_dataset`**

In `core/app/mcp/tools.py`, add the tool inside `register_tools`, right after `run_analytics_query`:

```python
    @server.tool()
    async def explain_dataset(ctx: Context, datasetId: str) -> dict:
        """Describe a dataset's queryable fields before calling
        run_analytics_query — author metadata (columns/timeField/
        reactsToExtent) plus introspected field name+type, so an agent
        doesn't have to guess a groupBy/measure field name. No stats, no
        sampling. SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=datasetId)
            assert item is not None
            base = {
                "title": item.title,
                "source": payload.source,
                "timeField": payload.timeField,
                "reactsToExtent": payload.reactsToExtent,
                "columns": {k: v.model_dump() for k, v in payload.columns.items()},
            }

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = _require_collection_read(session, user=user, collection_id=payload.collectionId)
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound:
                    raise ValueError("collection backing table not found")
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason)
                schema = table_info_to_schema(info)
                fields = [{"name": f["name"], "type": f["type"]} for f in schema["fields"]]
                return {**base, "fields": fields}

            external_url = _resolve_arcgis_external_url(session, user=user, dataset_item_id=datasetId)
            client = harvest_routes.get_arcgis_http_client()
            try:
                response = client.get(f"{external_url}?f=json")
                response.raise_for_status()
            except EgressBlockedError:
                raise ValueError("arcgis service unavailable")
            except httpx.HTTPError:
                raise ValueError("arcgis service unavailable")
            finally:
                client.close()
            data = response.json()
            raw_fields = data.get("fields") if isinstance(data, dict) else None
            fields = [
                {"name": f.get("name"), "type": f.get("type")}
                for f in (raw_fields or []) if isinstance(f, dict)
            ]
            return {**base, "fields": fields}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_explain_dataset.py tests/test_mcp_tools_explain_dataset_arcgis.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_explain_dataset.py core/tests/test_mcp_tools_explain_dataset_arcgis.py
git commit -m "feat(core): mcp explain_dataset tool (SP-14l)"
```

---

