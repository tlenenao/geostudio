# SP-14l — MCP analytique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three MCP tools — `create_dataset`, `run_analytics_query`, `explain_dataset` — that let an agent create a shared dataset (source `collection` or `arcgis`), discover its queryable fields, and run structured aggregate queries against it, all in `core/app/mcp/tools.py`.

**Architecture:** Each tool **mirrors** an existing, already-tested REST route (`POST /configs` kind=dataset, `POST /collections/{id}/aggregate`, `POST /datasets/{id}/arcgis/aggregate`), reusing the same repository/service-layer calls the routes use, with route-private permission/validation helpers **reimplemented** inline (not cross-imported) so their `HTTPException` becomes `ValueError` — the same pattern the file's 12 existing tools already use (`_require_access`, `_require_collection_read`, `_validate_extension_scope`). No new abstraction layer, no REST route changes.

**Tech Stack:** FastAPI + `mcp.server.fastmcp.FastMCP` (existing `core/app/mcp/` module), SQLAlchemy, DuckDB (via `app.analytics.aggregate`), httpx (via `app.harvest.live_query`/`app.harvest.egress`), pytest.

## Global Constraints

- Design is locked by `docs/superpowers/specs/2026-08-04-sp14l-mcp-analytique-design.md` — do not re-litigate scope (exactly 3 tools, no `run_sql`, no requête visuelle, no per-field stats in `explain_dataset`).
- `run_analytics_query` requires only dataset read access (no analyst role) — confirmed design decision.
- Every write tool (`create_dataset`) is gated by `is_read_only_mode()` and added to `READ_ONLY_TOOLS`.
- Domain exceptions at the tool boundary become `ValueError` (FastMCP has no HTTP status channel) — never let `HTTPException` escape a tool body.
- Docs/commit messages in French, code/identifiers in English (repo convention, `CLAUDE.md`).
- Conventional commits, one subject per commit (`feat(core): …`).
- `core/tests/` — run tests with `cd core && uv run pytest <path> -v`. Tests marked `pytest.mark.postgis` require `CORE_TEST_DATABASE_URL` (real PostGIS) — the test runner in this environment has it set; if a `-v` run reports `SKIPPED (postgis…)`, stop and flag it rather than treating the task as done.

---

## Context every task needs

**`core/app/mcp/tools.py`** registers all MCP tools inside `register_tools(server, session_factory)`. Every tool:
1. Calls `get_access_token()` then opens `with request_scoped_session(session_factory) as session:`.
2. Resolves the caller via `_resolve_actor(session, access_token)` → `User`.
3. Does its work, raising `ValueError` (never `HTTPException`) on any failure — FastMCP turns an uncaught exception in a tool body into an `isError=true` result automatically.

Existing private helpers already in the file (do not duplicate, reuse as-is):
- `_resolve_actor(session, access_token) -> User`
- `_require_access(session, *, user, item_id, action) -> ItemAccessFacts` — read/write check on any item.
- `_require_collection_read(session, *, user, collection_id) -> Collection` — read check on a collection.
- `_validate_extension_scope(session, config, *, tenant_id) -> None`

**Reused core APIs** (all already exist, unmodified by this plan):
- `app.configs.schemas.DatasetPayload` / `DatasetColumnMeta` / `BuilderConfig` (`kind="dataset"`, `dataset: DatasetPayload`).
- `app.configs.dataset_validation.validate_dataset_payload(session, config, user=user)` — raises `HTTPException(422, detail=str)` per source (`app.collections.dataset_validation`/`app.harvest.dataset_validation` register the two validators at `app.main` import time — already wired, nothing to change).
- `app.analytics.aggregate.AggregateRequestBody` / `AggregateMeasure` / `UnknownAggregateField` / `run_collection_aggregate(conn, *, base_uri, tenant_id, collection_id, table_info, request)`.
- `app.features.routes.get_duckdb_connection_factory()` / `get_analytics_base_uri()` — plain functions (read env vars), called directly (not via FastAPI `Depends`, since MCP tool bodies aren't routes). Import the **module** (`from app.features import routes as features_routes`) and call `features_routes.get_duckdb_connection_factory()` — this is what makes them monkeypatchable in tests via `monkeypatch.setattr(features_routes, "get_duckdb_connection_factory", fake)`, mirroring what `app.dependency_overrides[...]` does for the REST route.
- `app.harvest.routes.get_arcgis_http_client()` — same pattern, import the module (`from app.harvest import routes as harvest_routes`), call `harvest_routes.get_arcgis_http_client()`.
- `app.harvest.live_query.translate_aggregate_query` / `fetch_query` / `aggregate_response` / `ArcgisQueryError`.
- `app.harvest.egress.EgressBlockedError`.
- `app.harvest.repository.get_feature_layer_record(session, *, tenant_id, item_id)`.
- `app.collections.introspection_pg.introspect_table` / `app.collections.schema_json.table_info_to_schema` (both already imported in `tools.py`).
- Import-linter contract (`core/pyproject.toml` `[tool.importlinter]`) already permits `app.mcp` → `app.features`/`app.harvest`/`app.collections`/`app.configs` (layer order: `app.mcp` sits just below `app.main`, above everything else touched here) — no contract change needed. Verified in Task 4.

---

### Task 1: `create_dataset` tool

**Files:**
- Modify: `core/app/mcp/tools.py`
- Modify: `core/tests/test_mcp_read_only_mode.py` (extend the existing generic read-only-mode coverage — this file already asserts `READ_ONLY_TOOLS` equals an exact set of 4 tool names; adding a 5th tool without updating it would break that test)
- Test: `core/tests/test_mcp_tools_dataset_create.py` (new)

**Interfaces:**
- Produces: MCP tool `create_dataset(ctx, title: str, source: Literal["collection","arcgis"], collectionId: str | None = None, arcgisItemId: str | None = None, columns: dict[str, DatasetColumnMeta] | None = None, timeField: str | None = None, reactsToExtent: bool = False) -> ItemRead`.
- Produces: private helper `_validate_dataset(session, config: BuilderConfig, *, user: User) -> None` (raises `ValueError`), reused by no other task.
- `"create_dataset"` added to `READ_ONLY_TOOLS`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_mcp_tools_dataset_create.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""create_dataset (SP-14l) — mirrors POST /configs with kind="dataset":
same DatasetPayload construction, same per-source readability validation
(app.configs.dataset_validation) as the REST route. SQLite is enough here —
neither source variant needs real PostGIS introspection at creation time,
only catalog metadata (Collection row / harvested "external" item row)."""
from sqlalchemy import select

from app.audit.models import AuditLog
from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401


def _register_collection(app_client, *, public=True, owner=None):
    with app_client.session_factory() as session:
        col = collections_repo.create_collection(
            session, tenant_id=app_client.tenant.id, owner_id=(owner or app_client.mock_user).id,
            table_name="incidents", title="Incidents", description="", is_public=public,
            pk_column="id", geometry_column="geom", geometry_type="Point", srid=4326,
        )
        session.commit()
        return col.id


def _register_arcgis_layer(app_client, *, public=True, owner=None):
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
        if public:
            items_repo.set_is_public(
                session, tenant_id=app_client.tenant.id, item_id=layer_item.id, is_public=True,
            )
        harvest_repo.create_record(
            session, tenant_id=app_client.tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0",
            layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def test_create_dataset_collection_source_creates_item_and_config(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.kind == "dataset"
        assert config.config.dataset.source == "collection"
        assert config.config.dataset.collectionId == collection_id


def test_create_dataset_arcgis_source_creates_item_and_config(app_client):
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.source == "arcgis"
        assert config.config.dataset.arcgisItemId == arcgis_item_id


def test_create_dataset_accepts_columns_time_field_and_reacts_to_extent(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
            "columns": {"titre": {"label": "Titre", "description": None, "format": None}},
            "timeField": "created_at", "reactsToExtent": True,
        })

    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.columns["titre"].label == "Titre"
        assert config.config.dataset.timeField == "created_at"
        assert config.config.dataset.reactsToExtent is True


def test_create_dataset_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    with app_client.session_factory() as session:
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)


def test_create_dataset_unreadable_collection_errors_without_leaking_existence(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd-sub",
            username="otherowner-cd", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        collection_id = _register_collection(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })
    assert "not found" in error_text


def test_create_dataset_unreadable_arcgis_layer_errors(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd2-sub",
            username="otherowner-cd2", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })
    assert "not found" in error_text
```

Extend `core/tests/test_mcp_read_only_mode.py`:

```python
def test_read_only_tools_constant_matches_the_five_write_tools():
    assert READ_ONLY_TOOLS == {
        "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
    }
```

Replace the old `test_read_only_tools_constant_matches_the_four_write_tools` with the function above (same file, same fixtures — just the one function body and its name change), and add this new test right after `test_create_form_app_refuses_in_read_only_mode`:

```python
def test_create_dataset_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_dataset",
            {"title": "X", "source": "collection", "collectionId": "does-not-exist"},
        )
    assert READ_ONLY_MESSAGE in error_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_dataset_create.py tests/test_mcp_read_only_mode.py -v`
Expected: `test_mcp_tools_dataset_create.py` fails with something like `AssertionError: tool create_dataset errored: ... Unknown tool: create_dataset` (or a `ValueError`/`KeyError` from FastMCP about an unregistered tool name). `test_read_only_tools_constant_matches_the_five_write_tools` fails because `READ_ONLY_TOOLS` still has 4 entries. `test_create_dataset_refuses_in_read_only_mode` fails the same "unknown tool" way.

- [ ] **Step 3: Implement `create_dataset`**

In `core/app/mcp/tools.py`, add to the imports at the top:

```python
from fastapi import HTTPException

from app.configs.dataset_validation import validate_dataset_payload
from app.configs.schemas import DatasetColumnMeta, DatasetPayload
```

(`BuilderConfig`, `Literal`, `items_repo`, `configs_repo`, `write_audit`, `is_read_only_mode` are already imported.)

Change the `READ_ONLY_TOOLS` line to:

```python
READ_ONLY_TOOLS = {"save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset"}
```

Add this private helper right after `_validate_extension_scope` (same file, module level, before `_parse_bbox_tuple`):

```python
def _validate_dataset(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors app/configs/routes.py's call to validate_dataset_payload — same
    per-source (collection/arcgis) readability check the REST route runs on
    POST /configs and PUT /configs/{by-item} — but raises ValueError instead
    of HTTPException, same rationale as _require_access above. Without this
    call, create_dataset could create a dataset pointing at a collection or
    arcgis layer invisible to the caller."""
    try:
        validate_dataset_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
```

Add the tool itself inside `register_tools`, right after `create_form_app` and before `get_sharing`:

```python
    @server.tool()
    async def create_dataset(
        ctx: Context,
        title: str,
        source: Literal["collection", "arcgis"],
        collectionId: str | None = None,
        arcgisItemId: str | None = None,
        columns: dict[str, DatasetColumnMeta] | None = None,
        timeField: str | None = None,
        reactsToExtent: bool = False,
    ) -> ItemRead:
        """Create a shared dataset (source collection or arcgis) — mirrors
        POST /configs with kind="dataset" (the path
        itemClient.ts::createDatasetItem uses). SP-14l."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = DatasetPayload(
                source=source, collectionId=collectionId, arcgisItemId=arcgisItemId,
                columns=columns or {}, timeField=timeField, reactsToExtent=reactsToExtent,
            )
            config = BuilderConfig(version=1, kind="dataset", dataset=payload)
            _validate_dataset(session, config, user=user)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="dataset", title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": "dataset"},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_dataset_create.py tests/test_mcp_read_only_mode.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_dataset_create.py core/tests/test_mcp_read_only_mode.py
git commit -m "feat(core): mcp create_dataset tool (SP-14l)"
```

---

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

### Task 4: Full verification

**Files:** none modified — verification only.

**Interfaces:** none (terminal task).

- [ ] **Step 1: Run the full core test suite**

Run: `cd core && uv run pytest -v`
Expected: every test PASSES or is explicitly `SKIPPED` for a documented reason (`postgis: nécessite un PostGIS réel` when `CORE_TEST_DATABASE_URL` is unset). If any of the new `test_mcp_tools_*` files show as skipped in an environment where `CORE_TEST_DATABASE_URL` **is** set, stop — that means the `postgis` marker was misapplied (a file that doesn't actually need PostGIS shouldn't carry it, or one that does isn't getting picked up) and needs fixing before this task can be marked done.

- [ ] **Step 2: Run import-linter to confirm no layering violation**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — confirms `app.mcp`'s new imports (`app.features.routes`, `app.harvest.routes`, `app.harvest.live_query`, `app.harvest.repository`, `app.harvest.egress`, `app.configs.dataset_validation`) all sit in layers below `app.mcp`, per the existing `[tool.importlinter]` contract in `core/pyproject.toml` (already verified during planning — this step is the executable confirmation).

- [ ] **Step 3: Smoke-test tool registration count**

Run:
```bash
cd core && uv run python3 -c "
from app.mcp.server import create_mcp_server
import asyncio

async def main():
    server = create_mcp_server('http://localhost:8200', lambda: None)
    tools = await server.list_tools()
    names = sorted(t.name for t in tools)
    print(names)
    assert {'create_dataset', 'run_analytics_query', 'explain_dataset'} <= set(names)
    assert len(names) == 15

asyncio.run(main())
"
```
Expected: prints a sorted list of 15 tool names including the 3 new ones (12 existing + `create_dataset` + `run_analytics_query` + `explain_dataset`), no assertion error. (`session_factory=lambda: None` is safe here — `list_tools()` only reads the registered tool metadata, it never opens a session.)

- [ ] **Step 4: Update CLAUDE.md's roadmap section**

Modify `CLAUDE.md`, in the "### À venir" section under "Feuille de route (état d'avancement)": move the SP-14l line from implied/future into the "### Fait" section, following the exact style of the SP-14k entry already there (`- **SP-14k** — ... **A22 complet...**.` pattern). Add, right after the `SP-13` bullet and before the existing `SP-14` planning note is removed:

```markdown
- **SP-14l** — MCP analytique : outils `create_dataset`, `run_analytics_query`,
  `explain_dataset`, câblés sur les chemins de requête dataset déjà validés
  (SP-11b, SP-14a/k).
```

Remove the now-stale `- **SP-14** — Analytics UX (...). Jalon M11.` line from `### À venir` only if this was the last outstanding SP-14 sub-part — check `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-14 "Contenu" against what's shipped (datasets partagés ✅ SP-14a, contexte analytique ✅ SP-14b, widgets analytiques ✅ SP-14c–j, SQL Lab ✅ SP-14i, source arcgis ✅ SP-14k, MCP ✅ SP-14l) — **requête visuelle is still missing** (blocked on SP-15, per the design doc's non-buts), so SP-14 as a whole is **not** complete yet. Leave the `### À venir` line as-is; do not mark jalon M11 reached.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: SP-14l livré — mcp analytique (create_dataset, run_analytics_query, explain_dataset)"
```

---

## Self-Review

**Spec coverage:** §2 `create_dataset` → Task 1. §3 `run_analytics_query` → Task 2. §4 `explain_dataset` → Task 3. §5 (mirroring, not extraction) → followed throughout (every helper reimplements route logic rather than importing private `_`-prefixed names; only non-underscored "factory" functions — `get_duckdb_connection_factory`, `get_analytics_base_uri`, `get_arcgis_http_client` — are called via module reference). §6 (permissions: dataset read ≠ data read, re-checked independently) → covered by `_resolve_arcgis_external_url`'s independent check + the `test_run_analytics_query_collection_unreadable_by_caller_errors`/`test_run_analytics_query_arcgis_layer_unreadable_errors` tests. §7 (no audit on reads) → `run_analytics_query`/`explain_dataset` write no audit rows, matching `aggregate_features`/`query_features`. §8 risks table → each row maps to a test or an explicit design choice already reflected in the code above.

**Placeholder scan:** no TBD/TODO; every step shows complete code; no "similar to Task N" references (Task 3's tests are fully written out despite structural similarity to Task 2's, since the exact assertions/fixtures differ).

**Type consistency:** `DatasetPayload`/`DatasetColumnMeta` used identically across Tasks 1–3 (as defined in `app.configs.schemas`, unmodified). `_resolve_dataset_payload` (Task 2) and `_resolve_arcgis_external_url` (Task 2) signatures match their Task 3 call sites exactly. `run_analytics_query`'s return shape (`{"categoryKey", "rows"}`) matches what Task 2's tests assert. `explain_dataset`'s return shape matches what Task 3's tests assert.
