# Task 2 report — `run_analytics_query` MCP tool (SP-14l)

## What was implemented

`core/app/mcp/tools.py` (after Task 1's `create_dataset`/`_validate_dataset`):

- Imports added: `httpx`, `app.analytics.aggregate.{AggregateMeasure, AggregateRequestBody,
  UnknownAggregateField, run_collection_aggregate}`, `app.features.routes as features_routes`,
  `app.harvest.live_query`, `app.harvest.repository as harvest_repo`,
  `app.harvest.routes as harvest_routes`, `app.harvest.egress.EgressBlockedError`.
- Two new private helpers, placed right after `_validate_dataset`:
  - `_resolve_dataset_payload(session, *, user, dataset_item_id) -> DatasetPayload` — read-access
    check on the dataset item + kind/payload extraction. Reused by Task 3 (`explain_dataset`).
  - `_resolve_arcgis_external_url(session, *, user, dataset_item_id) -> str` — independent
    double permission check (dataset item read, then arcgis layer item read), mirroring
    `app/harvest/routes.py::_resolve_arcgis_dataset` line for line but raising `ValueError`
    instead of `HTTPException` (same rationale as the existing `_require_access`). Also reused
    by Task 3.
- The `run_analytics_query` tool itself, registered right after `create_dataset`: dispatches on
  `payload.source` — `collection` goes through `introspect_table` + DuckDB
  (`run_collection_aggregate`, using `features_routes.get_duckdb_connection_factory()` /
  `get_analytics_base_uri()` called as plain functions, matching how the REST route's own
  `Depends` resolve); `arcgis` rejects `bucket`/`split`/`bins`, resolves the external URL via the
  new helper, and reuses `live_query.translate_aggregate_query` / `fetch_query` /
  `aggregate_response` exactly as `POST /datasets/{id}/arcgis/aggregate` does — so the SP-14k
  `where=` field-name validation fix in `translate_aggregate_query` is inherited automatically,
  no new validation logic was added.
- No `READ_ONLY_TOOLS` entry (this is a read-only tool, confirmed by
  `test_read_only_tools_constant_matches_the_five_write_tools` still passing unchanged).

Two new test files, transcribed from the brief with two deviations found and fixed during TDD
(see "Self-review findings" below):

- `core/tests/test_mcp_tools_run_analytics_query.py` (source `collection`, `@pytest.mark.postgis`)
- `core/tests/test_mcp_tools_run_analytics_query_arcgis.py` (source `arcgis`, SQLite/mock)

## What was tested and results

Ran with `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test` exported
(verified working against the running `postgis-test` container).

- Both new test files together: **7 passed, 0 skipped, 0 failed.**
  - `test_mcp_tools_run_analytics_query.py` — 4 tests, all `@pytest.mark.postgis`, all ran for
    real against Postgres/PostGIS (not skipped) — confirmed by watching them fail during RED
    (real DB writes/reads happening) and pass during GREEN, with no "skip" lines in the pytest
    summary.
  - `test_mcp_tools_run_analytics_query_arcgis.py` — 3 tests, SQLite-backed, no postgis marker.
- Step 6 regression suite (`test_mcp_tools_create.py`, `test_mcp_tools_create_form_app.py`,
  `test_mcp_tools_query_features.py`, `test_mcp_read_only_mode.py`,
  `test_mcp_tools_dataset_create.py`): **25 passed, 0 failed.**
- Combined final run of all 7 new + 25 regression tests together: **32 passed**, clean
  (`filterwarnings = ["error", ...]` is active project-wide — a stray warning would have failed
  the run outright; none did).
- `uv run lint-imports`: contract kept (0 broken) — the new cross-module imports
  (`app.harvest`, `app.features.routes`, `app.analytics.aggregate`) don't violate the module
  boundary lint.

## TDD Evidence

**RED** — before writing the implementation (imports/helpers/tool), ran:

```
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test \
  uv run pytest tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_run_analytics_query_arcgis.py -v
```

Result: **7 failed** (all 7 tests). Failure mode: `WARNING mcp.server.lowlevel.server: Tool
'run_analytics_query' not listed, no validation will be performed` followed by
`call_tool`/`call_tool_expecting_error` failing because the tool didn't exist yet (either an
unhandled/unknown-tool error path, or an unexpected `isError` value) — exactly the "unknown
tool" failure the brief predicted for Step 3.

**GREEN** — after implementing the tool/helpers and fixing the two test-file issues below, same
command:

```
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test \
  uv run pytest tests/test_mcp_tools_run_analytics_query.py tests/test_mcp_tools_run_analytics_query_arcgis.py -v
```

Result:
```
tests/test_mcp_tools_run_analytics_query.py::test_run_analytics_query_collection_source_returns_grouped_counts PASSED
tests/test_mcp_tools_run_analytics_query.py::test_run_analytics_query_unknown_group_by_field_errors PASSED
tests/test_mcp_tools_run_analytics_query.py::test_run_analytics_query_dataset_not_found_errors PASSED
tests/test_mcp_tools_run_analytics_query.py::test_run_analytics_query_collection_unreadable_by_caller_errors PASSED
tests/test_mcp_tools_run_analytics_query_arcgis.py::test_run_analytics_query_arcgis_source_groupby_and_measure PASSED
tests/test_mcp_tools_run_analytics_query_arcgis.py::test_run_analytics_query_arcgis_source_rejects_bucket PASSED
tests/test_mcp_tools_run_analytics_query_arcgis.py::test_run_analytics_query_arcgis_layer_unreadable_errors PASSED
7 passed in 3.22s
```

Step 6 regression command and result:
```
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test \
  uv run pytest tests/test_mcp_tools_create.py tests/test_mcp_tools_create_form_app.py \
  tests/test_mcp_tools_query_features.py tests/test_mcp_read_only_mode.py \
  tests/test_mcp_tools_dataset_create.py -v
# 25 passed in 5.89s
```

## Files changed

- `core/app/mcp/tools.py` — imports, `_resolve_dataset_payload`, `_resolve_arcgis_external_url`,
  `run_analytics_query` tool.
- `core/tests/test_mcp_tools_run_analytics_query.py` — new.
- `core/tests/test_mcp_tools_run_analytics_query_arcgis.py` — new (transcribed verbatim from the
  brief, no changes needed).

Commit: `d877944` — `feat(core): mcp run_analytics_query tool (SP-14l)`.

## Self-review findings

- Implementation (`tools.py`) matches the brief's literal code exactly — no additions beyond
  scope (no analyst-role check, no `run_sql`, `run_analytics_query` correctly omitted from
  `READ_ONLY_TOOLS`).
- No `HTTPException` escapes the tool body: every error path in the new helpers and the tool
  itself raises `ValueError`, consistent with every other tool in this file.
- `_resolve_arcgis_external_url` double-checks both the dataset item and the underlying arcgis
  layer item read access, independently of `_resolve_dataset_payload`'s own dataset-item check —
  exactly mirrors `app/harvest/routes.py::_resolve_arcgis_dataset`. Confirmed via
  `test_run_analytics_query_arcgis_layer_unreadable_errors`, which registers the arcgis layer
  item under a *different* owner (not `mock_user`) with no share, and confirms `run_analytics_query`
  refuses it even though the dataset item itself is owned by (and thus readable to) the caller.
- The arcgis-side injection-relevant piece (`translate_aggregate_query`'s field-name validation
  fixed under SP-14k) is reused as-is — no new validation logic was written, per the brief.
- Two issues found in the brief's literal test code during RED→GREEN iteration (both in
  `test_mcp_tools_run_analytics_query.py`, the postgis-marked file — the arcgis test file needed
  no changes):
  1. **Double `with app_client:` per test.** The brief's tests exit and re-enter
     `with app_client:` within a single test function. `mcp.server.streamable_http_manager.
     StreamableHTTPSessionManager.run()` (the ASGI app's lifespan) can only run once per
     instance — re-entering `with app_client:` a second time on the same `TestClient`/app raises
     `RuntimeError: StreamableHTTPSessionManager .run() can only be called once per instance.`
     This is a hard library restriction (source-code-documented), not a decision to relitigate.
     Fix: collapsed each test's two-or-three `with app_client:` blocks into one — nothing in
     between (`_register_incidents_collection`, `_write_partition`, the `session_factory()`
     privacy flip) actually needs the ASGI lifespan; only the `call_tool`/`call_tool_expecting_error`
     calls do.
  2. **Ownership short-circuit made `test_run_analytics_query_collection_unreadable_by_caller_errors`
     untestable as written.** The brief reused `_register_incidents_collection` (owner =
     `mock_user`, the caller) then flipped `is_public=False` expecting the caller to lose read
     access. But `app/sharing/authorization.py::can()` short-circuits
     `if item.owner_id == user_id: return True` *before* checking `is_public` — so an owner's
     read access can never be revoked by flipping `is_public`. As observed, this made the tool
     legitimately succeed (`isError: False`, returning `{"categoryKey": "titre", "rows": []}`)
     where the test expected an error. Fix: added `_register_incidents_collection_owned_by_other`,
     a near-duplicate of `_register_incidents_collection` that creates the collection under a
     *different* owner (public at creation, so `create_dataset` still succeeds for the caller),
     so the later `is_public=False` flip genuinely revokes the caller's collection-read access
     while the dataset item — owned by the caller — stays readable, exactly as the test's own
     comment describes the intent.
  Both fixes are additive/corrective only; they don't touch `tools.py` or change what's being
  verified, they just make the tests actually exercise what they claim to.

## Issues or concerns

- The two test-file deviations above are documented inline in the test file itself (as code
  comments) and summarized here for visibility, per the instruction to flag anything that
  required a judgment call beyond literal transcription. Both are test-infrastructure/test-logic
  fixes, not decisions about `tools.py`'s behavior — the implementation itself required no
  deviation from the brief.
- Noted but out of scope: several unrelated `.superpowers/sdd/*.md` files
  (`progress.md`, `task-1-brief.md`, `task-1-report.md`, `task-2-brief.md`) showed up as modified
  in `git status` at the start of this task, and `task-2-report.md` already existed with content
  from an unrelated prior SP-14k task (`harvest_repo.get/list_feature_layer_record`). None of
  these were touched by this task's work; `task-2-report.md` is overwritten here with this task's
  own report, and only `core/app/mcp/tools.py` plus the two new test files were staged/committed.
- No other concerns. All tests pass, no regressions, import-linter clean, no stray warnings.
