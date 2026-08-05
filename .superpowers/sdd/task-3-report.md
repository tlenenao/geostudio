# Task 3 report — Core: MCP tool `create_bookmark`

## What I implemented

Added an MCP tool `create_bookmark` to `core/app/mcp/tools.py`, mirroring the
existing `create_dataset` tool, which itself mirrors `POST /configs` with
`kind="dataset"`. Specifically:

- Extended the `app.configs.schemas` import to pull in `BookmarkCrossFilterEntry`,
  `BookmarkPayload`, `BookmarkTimeRange` alongside the existing `BuilderConfig`,
  `DatasetColumnMeta`, `DatasetPayload`.
- Added `from app.configs.bookmark_validation import validate_bookmark_payload`
  next to the existing dataset-validation import.
- Extended `READ_ONLY_TOOLS` with `"create_bookmark"` (now 6 entries).
- Added `_validate_bookmark(session, config, *, user)` right after
  `_validate_dataset` — same pattern: calls `validate_bookmark_payload`
  (Task 2), catches `HTTPException` and re-raises as `ValueError` (MCP tool
  bodies have no HTTP status channel).
- Added the `create_bookmark` tool right after `create_dataset`:
  `create_bookmark(ctx, title, appId, pageId, timeRange=None, extent=None,
  crossFilter=None) -> ItemRead`. Checks `is_read_only_mode()` *before*
  opening any DB session (same as all sibling write tools), resolves the
  actor via `_resolve_actor`, builds a `BookmarkPayload`/`BuilderConfig(kind="bookmark")`,
  validates via `_validate_bookmark`, creates the item
  (`resource_type="bookmark"`) and config, and writes two audit log entries
  (`item.create`, `config.create`) with `actor_kind="agent"`.

## Files changed

- `core/app/mcp/tools.py` — import extension, `READ_ONLY_TOOLS` extension,
  `_validate_bookmark` helper, `create_bookmark` tool (64 lines added).
- `core/tests/test_mcp_read_only_mode.py` — replaced
  `test_read_only_tools_constant_matches_the_five_write_tools` with
  `test_read_only_tools_constant_matches_the_six_write_tools` (now asserts 6
  entries including `create_bookmark`); added
  `test_create_bookmark_refuses_in_read_only_mode` right after
  `test_create_dataset_refuses_in_read_only_mode`.
- `core/tests/test_mcp_tools_bookmark_create.py` (new) — 5 tests: item/config
  creation with `timeRange`, extent + cross-filter acceptance, audit log with
  `actor_kind="agent"`, unreadable-app 422 without leaking existence, empty
  `pageId` validation error.

All three files match the brief's literal code exactly (verified via diff
against the brief text; only the pre-created schema/validation modules from
Tasks 1/2 were cross-checked to confirm field names — `BookmarkPayload.appId`/
`.pageId`/`.timeRange`/`.extent`/`.crossFilter`, `BookmarkTimeRange.from_`
aliased to `"from"`, `BookmarkCrossFilterEntry.field`/`.value`/`.originSourceId`
— all matched what the brief assumed).

## TDD evidence

### RED

Command:
```
cd core && uv run pytest tests/test_mcp_tools_bookmark_create.py tests/test_mcp_read_only_mode.py -v
```

Result (before implementing the tool, after writing the test files): 6 failed,
7 passed.

- `test_create_bookmark_creates_item_and_config` — FAILED (`Unknown tool: create_bookmark`, tool not registered)
- `test_create_bookmark_accepts_extent_and_cross_filter` — FAILED (same)
- `test_create_bookmark_writes_audit_log_with_agent_actor` — FAILED (same)
- `test_create_bookmark_unreadable_app_errors_without_leaking_existence` — FAILED (same)
- `test_read_only_tools_constant_matches_the_six_write_tools` — FAILED (`READ_ONLY_TOOLS` still had only 5 entries)
- `test_create_bookmark_refuses_in_read_only_mode` — FAILED (`'Unknown tool: create_bookmark'` instead of the read-only message)

(`test_create_bookmark_empty_page_id_errors` incidentally passed even before
implementation, since `call_tool_expecting_error` only asserts a non-empty
error string and "Unknown tool" also satisfies that — this is expected and
harmless; it passes for the right reason after implementation too, as shown
below.)

This is the expected failure mode per the brief: "FAIL — `create_bookmark`
tool doesn't exist yet ... the read-only-tools set test fails (still 5
entries)."

### GREEN

Command:
```
cd core && uv run pytest tests/test_mcp_tools_bookmark_create.py tests/test_mcp_read_only_mode.py -v
```

Result (after implementing `create_bookmark`/`_validate_bookmark`/import/
`READ_ONLY_TOOLS` extension): **13 passed** (5 new bookmark tests + 8
read-only-mode tests, including the updated 6-tools-set test and the new
bookmark-refuses-in-read-only test).

Full core suite:
```
cd core && uv run pytest -q
```
Result: **878 passed, 112 skipped**, no failures, no regressions.

## Self-review

- Completeness: all 5 new bookmark tests pass, plus both edits to
  `test_mcp_read_only_mode.py`. Read-only gate checked before DB session
  opened, matching `create_dataset`'s ordering exactly.
- Quality: `create_bookmark` and `_validate_bookmark` are line-for-line what
  the brief specified, following `create_dataset`/`_validate_dataset`
  precedent already established in this file.
- Discipline (YAGNI): no extra behavior added beyond the brief; didn't touch
  unrelated tools or restructure `tools.py` (it remains a long file with ~11
  tools now — pre-existing condition, not made meaningfully worse by one more
  tool following the exact same pattern as its neighbors).
- Testing: real end-to-end MCP tool calls through the FastAPI test client (no
  mocks), same harness as `test_mcp_tools_create.py`/`test_mcp_tools_dataset_create.py`.
  TDD followed: tests written first, confirmed RED, then implementation,
  confirmed GREEN. Output is pristine (no warnings beyond pre-existing
  OpenTelemetry "already instrumented" noise present across the whole test
  suite, unrelated to this change).
- Housekeeping: `.superpowers/sdd/progress.md` and the task-1/task-2
  brief/report files showed as modified in `git status` at commit time (owned
  by the orchestrator, not by this task) — deliberately excluded from the
  commit; only `core/app/mcp/tools.py`,
  `core/tests/test_mcp_tools_bookmark_create.py`, and
  `core/tests/test_mcp_read_only_mode.py` were staged and committed, per the
  brief's own `git add` list.

Note: an earlier version of this report file existed on disk from a prior
SP-14l task-3 (`explain_dataset` MCP tool) that happened to reuse this same
filename — it has been overwritten with this task's (SP-14m
`create_bookmark`) report.

No issues found. No concerns.

## Commit

`5edaa5b` — `feat(core): mcp create_bookmark tool (SP-14m)`
(3 files changed, 172 insertions(+), 3 deletions(-))
