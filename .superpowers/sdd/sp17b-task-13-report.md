# Task 13 report: MCP `explain_report_schedule`

## What I implemented

Added a new MCP tool `explain_report_schedule(reportScheduleId: str) -> dict` to
`core/app/mcp/tools.py`, registered unconditionally (no `is_etl_enabled()`/
`is_export_enabled()` gate), placed immediately after `explain_alert_rule` and
before `get_sharing`, exactly per the brief's Step 3 literal code:

- import `from app.reports import repository as reports_repo` added next to the
  other domain-repository imports (alphabetically between `pipelines` and
  `sharing`).
- Tool body: resolves the report's config via `configs_repo.get_config_by_item`,
  requires `kind == "report"`, checks read access via `can()` against
  `items_repo.get_access_facts`, fetches the item, and returns
  `{title, bookmarkItemId, refreshPolicy, channels, lastRunAt}`, with
  `lastRunAt` sourced from `reports_repo.get_latest_run(...)`.
- All three "not found" branches raise the same `ValueError("report schedule
  not found")`, so a nonexistent id and an existing-but-unreadable id are
  indistinguishable to the caller (no existence leak) — mirrors
  `explain_alert_rule`.

### Test-harness correction (brief's Step 1 vs. reality)

The brief's illustrative Step 1 test used a `mcp_server_and_session` fixture and
`server.call_tool(...)` directly — **this fixture does not exist in this
codebase.** Per the controller's correction, I instead mirrored the real
harness from `core/tests/test_mcp_tools_alert.py`:

- Copied the `app_client(monkeypatch, tmp_path)` fixture verbatim (real FastAPI
  `TestClient` wired to a SQLite-backed session via `app.main.create_app()` +
  `app.db.get_session` override, returning `(client, Session, tenant_id,
  user_id)`).
- Used `call_tool(client, "explain_report_schedule", {...})` and
  `call_tool_expecting_error(client, "explain_report_schedule", {...})`
  imported from `tests.test_mcp_tools_create` (the same helpers
  `test_mcp_tools_alert.py` uses) — both take the raw `TestClient`, not a
  `Context`/session-factory pair.
- Wrote a local `_seed_report_schedule(Session, *, tenant_id, owner_id,
  with_run=True)` helper adapted from `_seed_alert_rule`: seeds a `report`
  item + `BuilderConfig` (kind `"report"`, with `bookmarkItemId`,
  `refreshPolicy`, `channels`) via `items_repo.create_item` /
  `configs_repo.create_config`, then seeds a `report_runs` row via
  `reports_repo.create_run(s, tenant_id=..., report_item_id=..., 
  export_job_id="job-1")` directly against the `Session` — not through the MCP
  tool itself.

## Tests written (`core/tests/test_mcp_tools_report.py`)

1. `test_explain_report_schedule_returns_the_schedule_shape` — seeds a report
   schedule with a run, calls the tool, asserts `title`, `bookmarkItemId`,
   `channels == ["webhook"]`, `refreshPolicy.cron`, and `lastRunAt is not
   None`.
2. `test_explain_report_schedule_404s_for_an_unreadable_schedule` — calls the
   tool with a nonexistent `reportScheduleId`, asserts the error text is
   `"report schedule not found"` via `call_tool_expecting_error`.

## RED/GREEN evidence

**RED** (before implementing the tool):
```
tests/test_mcp_tools_report.py::test_explain_report_schedule_returns_the_schedule_shape FAILED
tests/test_mcp_tools_report.py::test_explain_report_schedule_404s_for_an_unreadable_schedule FAILED
...
AssertionError: assert 'report schedule not found' in 'Unknown tool: explain_report_schedule'
2 failed in 2.13s
```
Both failed for the expected reason: the tool wasn't registered yet
(`Unknown tool: explain_report_schedule`).

**GREEN** (after implementing the tool):
```
cd core && uv run pytest tests/test_mcp_tools_report.py tests/test_mcp_tools_alert.py -v
tests/test_mcp_tools_report.py::test_explain_report_schedule_returns_the_schedule_shape PASSED
tests/test_mcp_tools_report.py::test_explain_report_schedule_404s_for_an_unreadable_schedule PASSED
tests/test_mcp_tools_alert.py::test_explain_alert_rule_returns_the_rule_shape PASSED
tests/test_mcp_tools_alert.py::test_explain_alert_rule_404s_for_an_unreadable_rule PASSED
4 passed in 2.50s
```

Also ran a broader regression sweep:
```
cd core && uv run pytest tests/ -k "mcp or report" -q
115 passed, 13 skipped, 1370 deselected in 15.66s
```
and `uv run lint-imports` — contract kept (170 files, 527 dependencies
analyzed, "layered architecture KEPT").

## Files changed

- `core/app/mcp/tools.py` — added `from app.reports import repository as
  reports_repo` import and the `explain_report_schedule` tool function
  (registered unconditionally, right after `explain_alert_rule`, before
  `get_sharing`).
- `core/tests/test_mcp_tools_report.py` — new file, 2 tests.

## Commit

`3b4bbd3` — `feat(core): MCP explain_report_schedule tool (SP-17b)`

## Self-review

- Used the REAL test harness (`app_client` fixture + `call_tool`/
  `call_tool_expecting_error`), not the brief's illustrative but nonexistent
  `mcp_server_and_session`/`server.call_tool` fixture. Confirmed.
- Tool registered unconditionally — no `is_etl_enabled()`/`is_export_enabled()`
  gate, verified by reading the diff.
- Not-found test correctly avoids leaking existence: all three failure paths
  (`kind != "report"`, no access facts / `can()` denies, item missing) raise
  the identical `ValueError("report schedule not found")` message — same as
  `explain_alert_rule`'s pattern.
- Test output is pristine (only pytest/OTel double-instrumentation warnings
  already present across the whole suite, unrelated to this change — same
  noise `test_mcp_tools_alert.py` produces).

No issues or concerns found. Left other unrelated pre-existing untracked/
modified files (`.superpowers/sdd/progress.md`, other task briefs/reports,
SP-17b spec/plan docs) out of this commit — not part of Task 13's scope.
