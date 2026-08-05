# Task 3 report — `explain_dataset` MCP tool (SP-14l)

## What was implemented

Added the `explain_dataset` MCP tool to `core/app/mcp/tools.py`, registered
inside `register_tools`, right after `run_analytics_query`. It is read-only
(no `READ_ONLY_TOOLS` entry needed — that set is for write-gating under demo
mode, not applicable here).

Behavior (verbatim from the brief, transcribed without changes):
- Resolves the dataset payload via `_resolve_dataset_payload` (Task 2 helper:
  read-access check + kind=="dataset" check).
- Fetches the item for its `title`.
- Builds a `base` dict: `title`, `source`, `timeField`, `reactsToExtent`,
  `columns` (author metadata, `DatasetColumnMeta.model_dump()` per column).
- For `source == "collection"`: re-checks collection read access
  (`_require_collection_read`), introspects the backing table
  (`introspect_table` → `TableNotFound`/`UnsupportedTable` mapped to
  `ValueError`), converts via `table_info_to_schema`, and returns
  `fields: [{name, type}]` — no stats, no sampling, per design non-buts.
- For `source == "arcgis"`: resolves the live external URL via
  `_resolve_arcgis_external_url` (Task 2 helper), does a live
  `GET {external_url}?f=json` through the egress-guarded
  `harvest_routes.get_arcgis_http_client()` (same seam as
  `run_analytics_query`'s arcgis path), maps `EgressBlockedError` /
  `httpx.HTTPError` to `ValueError("arcgis service unavailable")`, and
  extracts ArcGIS's standard layer `fields: [{name, type}]` from the
  `alias`-bearing `fields` array in the response (alias itself is dropped —
  brief only asks for name+type).

No new imports were needed: `introspect_table`, `table_info_to_schema`,
`TableNotFound`, `UnsupportedTable`, `harvest_routes`, `EgressBlockedError`,
`httpx`, `items_repo` were all already imported in `tools.py` from Tasks 1-2.
No new private helpers were added — `_resolve_dataset_payload` and
`_resolve_arcgis_external_url` were consumed as-is from Task 2.

## What was tested and results

Two new test files, both transcribed verbatim from the brief:

1. `core/tests/test_mcp_tools_explain_dataset.py` — source `collection`,
   marked `pytest.mark.postgis` (needs real PostGIS). **Ran for real, not
   skipped** — confirmed by exporting
   `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test`
   against the running `postgis-test` docker container before invoking
   pytest. Both tests in this file executed and passed against the real DB.
   - `test_explain_dataset_collection_source_returns_fields_and_metadata`
   - `test_explain_dataset_dataset_not_found_errors`

2. `core/tests/test_mcp_tools_explain_dataset_arcgis.py` — source `arcgis`,
   SQLite fixture, mocked `httpx` transport via `monkeypatch` on
   `harvest_routes.get_arcgis_http_client`.
   - `test_explain_dataset_arcgis_source_returns_fields_from_live_layer_metadata`

All 3 tests pass. No unexpected skips, no stray warnings (re-ran with
`-W error::DeprecationWarning`, clean). Also ran the full MCP test slice
(`pytest tests/ -k mcp -q`) for regression safety: **69 passed, 904
deselected**, no failures.

No brief-fidelity bugs were found in this task's test code (unlike Task 2,
which found two bugs in its own brief's test literal code). This task's
tests use a single `with app_client:` block per test (no re-entry issue),
and the "not found" test uses a nonexistent id rather than a caller-owned
resource, so there was no owner-short-circuit trap to hit either.

## TDD Evidence

### RED

Command:
```
cd core && export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test
uv run pytest tests/test_mcp_tools_explain_dataset.py tests/test_mcp_tools_explain_dataset_arcgis.py -v
```

Result: 3 failed (before implementation existed). Server logs show:
```
WARNING  mcp.server.lowlevel.server:server.py:494 Tool 'explain_dataset' not listed, no validation will be performed
```
followed by `call_tool` raising `AssertionError: tool explain_dataset
errored: ...` in all three tests — expected, since the tool didn't exist yet
and the MCP dispatcher returns an error result for an unregistered tool
name. (The `procrastinate.exceptions.AppNotOpen` tracebacks in the log are
pre-existing, caught-and-logged embedding-enqueue noise from
`create_dataset`'s item/collection creation, unrelated to this task — same
noise appears in Task 1/2's runs.)

### GREEN

Command (same as above), after implementing `explain_dataset`:
```
tests/test_mcp_tools_explain_dataset.py::test_explain_dataset_collection_source_returns_fields_and_metadata PASSED
tests/test_mcp_tools_explain_dataset.py::test_explain_dataset_dataset_not_found_errors PASSED
tests/test_mcp_tools_explain_dataset_arcgis.py::test_explain_dataset_arcgis_source_returns_fields_from_live_layer_metadata PASSED
3 passed in 2.11s
```

## Files changed

- `core/app/mcp/tools.py` — added `explain_dataset` tool (53 lines), no
  other lines touched (verified via `git diff -- app/mcp/tools.py`).
- `core/tests/test_mcp_tools_explain_dataset.py` — new file.
- `core/tests/test_mcp_tools_explain_dataset_arcgis.py` — new file.

Commit: `a1dc72a feat(core): mcp explain_dataset tool (SP-14l)`.

Note: several `.superpowers/sdd/*.md` files (progress.md, task-1/2/3
brief/report) showed as modified in `git status` at the start of this
session, before this task began — these were left untouched and NOT staged
or committed by this task; only `core/app/mcp/tools.py` and the two new
test files were added to the commit.

## Self-review findings

- Completeness: all 3 new tests pass; both files present as specified.
- Quality: no `HTTPException` escapes the tool body (both arcgis-path
  exception branches — `EgressBlockedError`, `httpx.HTTPError` — are caught
  and re-raised as `ValueError`, matching the rest of the file's
  convention). No stats/sampling/extra fields added beyond `name`+`type`
  per field, per design non-buts. Naming and structure match the existing
  tools' style (docstring convention, `with request_scoped_session(...)`,
  `base = {...}` then source-branch return).
- Discipline: implementation is a byte-for-byte transcription of the
  brief's Step 4 code block; no new private helpers, no new imports beyond
  what already existed.
- Testing: both test files are verbatim transcriptions from the brief;
  ran clean, no warnings, no skips, real PostGIS DB confirmed reachable and
  used.

## Issues or concerns

None. Task completed exactly as specified with no blockers.
