# Task 6 report: `app.appexport.miniserver.main`

## What I did

Followed TDD as instructed by the brief:

1. Read the full brief (`.superpowers/sdd/task-6-brief.md`).
2. Verified the actual current signatures of the four dependencies before writing
   any code, since the brief predates Task 5's review fix:
   - `core/app/appexport/miniserver/items.py` — confirmed `select_features`/
     `get_feature` signatures match the brief exactly, and confirmed the new
     `MissingGeometryColumn` exception: raised by `_build_where` when `bbox` or
     `geom_intersects` is passed against a `TableInfo` with `geometry_column is
     None`.
   - `core/app/appexport/manifest.py` — `read_manifest`/`CollectionSnapshotEntry`
     match the brief.
   - `core/app/analytics/aggregate.py` — `run_collection_aggregate` signature
     matches the brief (`conn, *, base_uri, tenant_id, collection_id, table_info,
     request`).
   - `core/app/analytics/duckdb_conn.py` — `open_local_connection()` exists
     exactly as the brief expects (spatial extension only, no S3 config).
3. Wrote `core/tests/test_appexport_miniserver_main.py` with the brief's 12
   tests verbatim, plus one additional test for the deviation
   (`test_list_items_bbox_on_non_spatial_collection_is_400`).
4. Ran the test file to confirm it failed with `ModuleNotFoundError` (13
   failures, all on the same import line) — matches the brief's expected Step 2
   outcome.
5. Created `core/app/appexport/miniserver/main.py` using the brief's Step 3
   content verbatim, with one deviation (see below): imported
   `MissingGeometryColumn` from `app.appexport.miniserver.items` and wrapped the
   `select_features` call in `list_items` with a nested `try/except` that raises
   `HTTPException(status_code=400, detail=str(exc))`.
6. Ran the test file again: all 13 passed.
7. Ran the three dependency test suites (Tasks 2, 3, 5): all 14 passed,
   confirming no regression.
8. Self-reviewed the diff (`git status`/`git diff --stat`) — confirmed only the
   two intended files are new/untracked; all other modified files in the
   working tree are pre-existing `.superpowers/sdd/*` scratch/bookkeeping files
   belonging to the controller's session, left untouched.
9. Staged only `core/app/appexport/miniserver/main.py` and
   `core/tests/test_appexport_miniserver_main.py` explicitly (no `-A`/`.`/`-a`)
   and committed.

## Test output

### `pytest tests/test_appexport_miniserver_main.py -v`

Before creating `main.py` (Step 2, expected failure):

```
collected 13 items
... (all 13 FAILED)
tests/test_appexport_miniserver_main.py:57: ModuleNotFoundError: No module named 'app.appexport.miniserver.main'
=========================== short test summary info ============================
FAILED tests/test_appexport_miniserver_main.py::test_geostudio_app_config_is_served
FAILED tests/test_appexport_miniserver_main.py::test_geostudio_connection_echoes_request_origin
FAILED tests/test_appexport_miniserver_main.py::test_list_collections_returns_manifest_entries
FAILED tests/test_appexport_miniserver_main.py::test_get_collection_includes_links
FAILED tests/test_appexport_miniserver_main.py::test_get_collection_missing_is_404
FAILED tests/test_appexport_miniserver_main.py::test_get_schema_returns_manifest_schema
FAILED tests/test_appexport_miniserver_main.py::test_list_items_reads_snapshot
FAILED tests/test_appexport_miniserver_main.py::test_get_single_item
FAILED tests/test_appexport_miniserver_main.py::test_get_single_item_missing_is_404
FAILED tests/test_appexport_miniserver_main.py::test_aggregate_counts_rows
FAILED tests/test_appexport_miniserver_main.py::test_aggregate_unknown_collection_is_404
FAILED tests/test_appexport_miniserver_main.py::test_static_runtime_is_served_at_root
FAILED tests/test_appexport_miniserver_main.py::test_list_items_bbox_on_non_spatial_collection_is_400
============================== 13 failed in 0.80s ==============================
```

After creating `main.py` (Step 4, expected pass):

```
collected 13 items

tests/test_appexport_miniserver_main.py::test_geostudio_app_config_is_served PASSED [  7%]
tests/test_appexport_miniserver_main.py::test_geostudio_connection_echoes_request_origin PASSED [ 15%]
tests/test_appexport_miniserver_main.py::test_list_collections_returns_manifest_entries PASSED [ 23%]
tests/test_appexport_miniserver_main.py::test_get_collection_includes_links PASSED [ 30%]
tests/test_appexport_miniserver_main.py::test_get_collection_missing_is_404 PASSED [ 38%]
tests/test_appexport_miniserver_main.py::test_get_schema_returns_manifest_schema PASSED [ 46%]
tests/test_appexport_miniserver_main.py::test_list_items_reads_snapshot PASSED [ 53%]
tests/test_appexport_miniserver_main.py::test_get_single_item PASSED     [ 61%]
tests/test_appexport_miniserver_main.py::test_get_single_item_missing_is_404 PASSED [ 69%]
tests/test_appexport_miniserver_main.py::test_aggregate_counts_rows PASSED [ 76%]
tests/test_appexport_miniserver_main.py::test_aggregate_unknown_collection_is_404 PASSED [ 84%]
tests/test_appexport_miniserver_main.py::test_static_runtime_is_served_at_root PASSED [ 92%]
tests/test_appexport_miniserver_main.py::test_list_items_bbox_on_non_spatial_collection_is_400 PASSED [100%]

============================== 13 passed in 1.06s ==============================
```

Note: the brief's own prose says "Expected: PASS (11 tests)" but the brief's
literal test-file code block actually contains 12 test functions (I counted
them individually: app_config, connection, list_collections, collection_links,
collection_missing_404, schema, list_items, single_item, single_item_missing_404,
aggregate_counts, aggregate_unknown_404, static_runtime = 12). This is a minor
miscount in the brief's own narrative text, not a code defect — my task
instructions said "11 from the brief + your 1 new one = 12" for the same
reason, and the actual total is 12 (brief) + 1 (mine) = 13, all passing. Not
treated as a deviation requiring action, just documented here for the
controller's awareness.

### `pytest tests/test_appexport_miniserver_items.py tests/test_analytics_duckdb_conn.py tests/test_appexport_manifest.py -v`

```
collected 14 items

tests/test_appexport_miniserver_items.py::test_select_features_reads_snapshot PASSED [  7%]
tests/test_appexport_miniserver_items.py::test_select_features_paginates PASSED [ 14%]
tests/test_appexport_miniserver_items.py::test_select_features_missing_collection_returns_empty_page PASSED [ 21%]
tests/test_appexport_miniserver_items.py::test_get_feature_returns_single_row PASSED [ 28%]
tests/test_appexport_miniserver_items.py::test_get_feature_missing_returns_none PASSED [ 35%]
tests/test_appexport_miniserver_items.py::test_select_features_bbox_on_non_spatial_raises_error PASSED [ 42%]
tests/test_appexport_miniserver_items.py::test_select_features_geom_intersects_on_non_spatial_raises_error PASSED [ 50%]
tests/test_analytics_duckdb_conn.py::test_open_connection_installs_and_loads_httpfs_and_spatial PASSED [ 57%]
tests/test_analytics_duckdb_conn.py::test_open_connection_configures_s3_settings_from_endpoint PASSED [ 64%]
tests/test_analytics_duckdb_conn.py::test_open_connection_detects_https_endpoint PASSED [ 71%]
tests/test_analytics_duckdb_conn.py::test_open_connection_installs_and_loads_h3 PASSED [ 78%]
tests/test_analytics_duckdb_conn.py::test_open_local_connection_installs_and_loads_spatial_only PASSED [ 85%]
tests/test_appexport_manifest.py::test_write_then_read_manifest_round_trips PASSED [ 92%]
tests/test_appexport_manifest.py::test_write_manifest_with_no_entries PASSED [100%]

============================== 14 passed in 1.24s ==============================
```

No regressions in Task 2 (`app.analytics.duckdb_conn`), Task 3
(`app.appexport.manifest`), or Task 5 (`app.appexport.miniserver.items`).

## Deviation from the brief (instructed)

The brief's literal Step 3 `list_items` route does not catch
`MissingGeometryColumn`, because that exception did not exist when this task's
brief was drafted — it was introduced by a Task 5 review fix afterward. Per the
controller's explicit instruction, I:

1. Read `core/app/appexport/miniserver/items.py` first and confirmed the
   current signature: `select_features(..., bbox=None, geom_intersects=None)`
   raises `MissingGeometryColumn("collection has no geometry column")` from
   `_build_where` when `bbox is not None or geom_intersects is not None` and
   `table_info.geometry_column is None`.
2. In `list_items` (the route accepting `bbox: str | None = None`), added
   `from app.appexport.miniserver.items import MissingGeometryColumn,
   get_feature, select_features` (extending the brief's import line) and
   wrapped the `select_features` call in a nested `try/except
   MissingGeometryColumn as exc: raise HTTPException(status_code=400,
   detail=str(exc))`, still inside the existing outer `try/finally: conn.close()`
   — so the connection is always closed before the exception propagates.
3. Added a 13th test, `test_list_items_bbox_on_non_spatial_collection_is_400`,
   using the existing `_client`/`_build_data_dir` fixtures from the brief
   unchanged: `col1`'s `TableInfo` already has `geometry_column=None` (visible
   directly in `_build_data_dir`), so no second manifest fixture was needed —
   I just issued a `bbox` query against the existing non-spatial `col1` and
   asserted `400`.

This is the only code deviation from the brief's literal Step 3 content. All
other code, including route ordering, response shapes, the static mount
placement as the last registered route, and the docstring, is copied verbatim
from the brief.

## Other deviations

None. File paths, module names, env var names
(`APPEXPORT_STANDALONE_DATA_DIR`/`APPEXPORT_STANDALONE_RUNTIME_DIR`), the
import-time (not per-request) read of `DATA_DIR`/`RUNTIME_DIR`, and the commit
message all match the brief.

## Self-review notes

- `git status --short` on the two target files showed `??` (untracked) before
  staging, confirming they are genuinely new files, not modifications.
- `git diff --stat` (unstaged, full working tree) showed only pre-existing
  modifications under `.superpowers/sdd/*` (controller's session bookkeeping,
  dated/versioned brief and report files for tasks 1-6) — none of which I
  touched or staged.
- Staged explicitly with `git add core/app/appexport/miniserver/main.py
  core/tests/test_appexport_miniserver_main.py` (no `-A`, `.`, or `-a`).
  Post-stage `git status --short` confirmed exactly those two files as `A`
  (added) and all `.superpowers/sdd/*` files remained `M` (unstaged modified),
  correctly excluded from this commit.
- Reviewed `main.py` logic once more end-to-end: route registration order
  keeps the catch-all static mount last (required by Starlette matching
  order, per the brief's own comment); every DuckDB connection opened in a
  route is closed in a `finally` block including on the new
  `MissingGeometryColumn` 400 path and the pre-existing
  `UnknownAggregateField` 400 path in `aggregate`; `_get_entry` correctly
  raises 404 before any DuckDB connection is opened for unknown collection
  IDs test coverage: `test_get_collection_missing_is_404`,
  `test_aggregate_unknown_collection_is_404`.
- No other files were modified; this task only creates new files as scoped.

## Commit

`d7f8f48` — `feat(core): standalone mini-server FastAPI app (SP-18c)` (plus a
body line documenting the `MissingGeometryColumn` deviation).

Files touched:
- `core/app/appexport/miniserver/main.py` (new)
- `core/tests/test_appexport_miniserver_main.py` (new)
