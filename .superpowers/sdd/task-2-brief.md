### Task 2: `run_analytics_query` tool

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_run_analytics_query.py` (new — source `collection`, needs real PostGIS)
- Test: `core/tests/test_mcp_tools_run_analytics_query_arcgis.py` (new — source `arcgis`, SQLite)

**Interfaces:**
- Consumes: `create_dataset` (Task 1) to build fixtures in tests.
- Produces: MCP tool `run_analytics_query(ctx, datasetId: str, query: AggregateRequestBody) -> dict` returning `{"categoryKey": str | list[str], "rows": list[dict]}`.
- Produces: private helper `_resolve_dataset_payload(session, *, user: User, dataset_item_id: str) -> DatasetPayload` — reused by Task 3.
- Produces: private helper `_resolve_arcgis_external_url(session, *, user: User, dataset_item_id: str) -> str` — reused by Task 3.

- [ ] **Step 1: Write the failing tests (collection source)**

Create `core/tests/test_mcp_tools_run_analytics_query.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""run_analytics_query, source "collection" (SP-14l) — mirrors POST
/collections/{id}/aggregate: same DuckDB/GeoParquet CDC read path
(app.analytics.aggregate.run_collection_aggregate). get_duckdb_connection_
factory/get_analytics_base_uri are called as plain functions inside the MCP
tool body (no FastAPI Depends there), so tests monkeypatch the
app.features.routes module attributes directly instead of using
app.dependency_overrides — same substitution app.dependency_overrides does
for the REST route's own test (test_features_aggregate_routes.py), just at
the Python-attribute level instead of the ASGI-DI level."""
import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.features import routes as features_routes

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import app_client, _register_incidents_collection  # noqa: F401

pytestmark = pytest.mark.postgis


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-04"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geom", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _fake_duckdb_factory():
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


@pytest.fixture(autouse=True)
def _local_duckdb(monkeypatch, tmp_path):
    monkeypatch.setattr(features_routes, "get_duckdb_connection_factory", lambda: _fake_duckdb_factory)
    monkeypatch.setattr(features_routes, "get_analytics_base_uri", lambda: str(tmp_path))
    return tmp_path


def _create_collection_dataset(app_client, collection_id):
    result = call_tool(app_client, "create_dataset", {
        "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
    })
    return result["pk"]


def test_run_analytics_query_collection_source_returns_grouped_counts(app_client, _local_duckdb):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
    _write_partition(_local_duckdb, tenant_id=app_client.tenant.id, collection_id=collection_id, rows=[
        {"id": 1, "tenant_id": app_client.tenant.id, "titre": "Nid de poule",
         "_op": "insert", "_lsn": 1, "_ts": 1.0, "geom": Point(2.3, 48.8)},
        {"id": 2, "tenant_id": app_client.tenant.id, "titre": "Nid de poule",
         "_op": "insert", "_lsn": 1, "_ts": 1.0, "geom": Point(2.3, 48.8)},
        {"id": 3, "tenant_id": app_client.tenant.id, "titre": "Lampadaire cassé",
         "_op": "insert", "_lsn": 1, "_ts": 1.0, "geom": Point(2.3, 48.8)},
    ])
    with app_client:
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        result = call_tool(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "titre"},
        })

    assert result["categoryKey"] == "titre"
    assert sorted(result["rows"], key=lambda r: r["titre"]) == [
        {"titre": "Lampadaire cassé", "value": 1}, {"titre": "Nid de poule", "value": 2},
    ]


def test_run_analytics_query_unknown_group_by_field_errors(app_client, _local_duckdb):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
    _write_partition(_local_duckdb, tenant_id=app_client.tenant.id, collection_id=collection_id, rows=[
        {"id": 1, "tenant_id": app_client.tenant.id, "titre": "Nid de poule",
         "_op": "insert", "_lsn": 1, "_ts": 1.0, "geom": Point(2.3, 48.8)},
    ])
    with app_client:
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        error_text = call_tool_expecting_error(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "inconnu"},
        })
    assert "inconnu" in error_text


def test_run_analytics_query_dataset_not_found_errors(app_client, _local_duckdb):
    with app_client:
        error_text = call_tool_expecting_error(app_client, "run_analytics_query", {
            "datasetId": "does-not-exist", "query": {"groupBy": "titre"},
        })
    assert "not found" in error_text


def test_run_analytics_query_collection_unreadable_by_caller_errors(app_client, _local_duckdb):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
    # Simulate the share being revoked after the dataset was created: flip
    # the collection private with no share, independent of the dataset item
    # (which stays readable — it's owned by mock_user).
    with app_client.session_factory() as session:
        from app.collections.models import Collection
        session.query(Collection).filter(Collection.id == collection_id).update({"is_public": False})
        session.commit()
    with app_client:
        error_text = call_tool_expecting_error(app_client, "run_analytics_query", {
            "datasetId": dataset_item_id, "query": {"groupBy": "titre"},
        })
    assert "not found" in error_text
```

- [ ] **Step 2: Write the failing tests (arcgis source)**

Create `core/tests/test_mcp_tools_run_analytics_query_arcgis.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_run_analytics_query_arcgis.py -v`
Expected: all FAIL — `run_analytics_query` tool does not exist yet (`isError` with an "unknown tool" style message, or the `call_tool`/`call_tool_expecting_error` helper raising because the tool name isn't registered).

- [ ] **Step 4: Implement `run_analytics_query`**

In `core/app/mcp/tools.py`, add to the imports:

```python
import httpx

from app.analytics.aggregate import AggregateMeasure, AggregateRequestBody, UnknownAggregateField, run_collection_aggregate
from app.features import routes as features_routes
from app.harvest import live_query
from app.harvest import repository as harvest_repo
from app.harvest import routes as harvest_routes
from app.harvest.egress import EgressBlockedError
```

Add these two private helpers, right after `_validate_dataset` (added in Task 1):

```python
def _resolve_dataset_payload(session, *, user: User, dataset_item_id: str) -> DatasetPayload:
    """Read-access check on the dataset item itself, plus its kind/payload —
    shared first step for run_analytics_query and explain_dataset (Task 3)."""
    _require_access(session, user=user, item_id=dataset_item_id, action="read")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if config is None or config.kind != "dataset" or config.config.dataset is None:
        raise ValueError("dataset not found")
    return config.config.dataset


def _resolve_arcgis_external_url(session, *, user: User, dataset_item_id: str) -> str:
    """Mirrors app/harvest/routes.py's _resolve_arcgis_dataset — same
    dataset-read-then-arcgis-layer-read double check as
    /datasets/{id}/arcgis/aggregate — but raises ValueError instead of
    HTTPException, same rationale as _require_access above. Re-checks
    dataset-item read access independently of _resolve_dataset_payload's
    own check (harmless, cheap, and keeps this a faithful, self-contained
    mirror of the REST route's helper rather than a partial reimplementation)."""
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=dataset_item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise ValueError("dataset not found")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if (
        config is None or config.kind != "dataset" or config.config.dataset is None
        or config.config.dataset.source != "arcgis"
    ):
        raise ValueError("dataset not found")
    arcgis_item_id = config.config.dataset.arcgisItemId
    assert arcgis_item_id is not None
    record = harvest_repo.get_feature_layer_record(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if record is None or record.external_url is None:
        raise ValueError("arcgis layer not found")
    layer_facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if layer_facts is None or not can(session, user_id=user.id, action="read", item=layer_facts):
        raise ValueError("arcgis layer not found")
    return record.external_url
```

Add the tool itself inside `register_tools`, right after `create_dataset`:

```python
    @server.tool()
    async def run_analytics_query(ctx: Context, datasetId: str, query: AggregateRequestBody) -> dict:
        """Run a structured aggregate query against a dataset (source
        collection or arcgis) — mirrors POST /collections/{id}/aggregate and
        POST /datasets/{id}/arcgis/aggregate, same query contract
        (groupBy/split/measures/filters/bbox/bucket/bins), same permissions.
        Never fabricates SQL (A19). SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = _require_collection_read(session, user=user, collection_id=payload.collectionId)
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound:
                    raise ValueError("collection backing table not found")
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason)
                conn = features_routes.get_duckdb_connection_factory()()
                try:
                    try:
                        category_key, rows = run_collection_aggregate(
                            conn, base_uri=features_routes.get_analytics_base_uri(),
                            tenant_id=col.tenant_id, collection_id=col.id,
                            table_info=info, request=query,
                        )
                    except UnknownAggregateField as exc:
                        raise ValueError(f"{exc.field}: {exc.message}")
                finally:
                    conn.close()
                return {"categoryKey": category_key, "rows": rows}

            assert payload.arcgisItemId is not None
            if query.bucket is not None or query.split is not None or query.bins is not None:
                raise ValueError("bucket/split/bins are not supported for arcgis-sourced datasets")
            external_url = _resolve_arcgis_external_url(session, user=user, dataset_item_id=datasetId)
            group_by = query.groupBy if isinstance(query.groupBy, list) else ([query.groupBy] if query.groupBy else [])
            measures_in = query.measures or [AggregateMeasure(field=query.field, agg=query.agg, label="value")]
            measures = [(m.agg, m.field, m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)) for m in measures_in]
            try:
                params = live_query.translate_aggregate_query(
                    group_by=group_by, measures=measures, filters=query.filters, bbox=query.bbox,
                )
            except live_query.ArcgisQueryError as exc:
                raise ValueError(f"{exc.field}: {exc.message}")
            client = harvest_routes.get_arcgis_http_client()
            try:
                raw = live_query.fetch_query(client, external_url, params)
            except EgressBlockedError:
                raise ValueError("arcgis service unavailable")
            except httpx.HTTPError:
                raise ValueError("arcgis service unavailable")
            finally:
                client.close()
            category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
            return {"categoryKey": category_key, "rows": rows}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_run_analytics_query_arcgis.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full existing MCP test suite to check for regressions**

Run: `cd core && uv run pytest tests/test_mcp_tools_create.py tests/test_mcp_tools_create_form_app.py tests/test_mcp_tools_query_features.py tests/test_mcp_read_only_mode.py tests/test_mcp_tools_dataset_create.py -v`
Expected: all PASS (no existing tool's behavior changed).

- [ ] **Step 7: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_run_analytics_query.py core/tests/test_mcp_tools_run_analytics_query_arcgis.py
git commit -m "feat(core): mcp run_analytics_query tool (SP-14l)"
```

---

