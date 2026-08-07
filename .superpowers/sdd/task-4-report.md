# Task 4 Report: `pipelines_repo.list_due_pipelines`

## Summary

Successfully implemented `list_due_pipelines(session: Session) -> list[tuple[str, str]]` in `core/app/pipelines/repository.py`. This function scans all tenant configurations for pipeline configs with enabled refresh policies, determines which are due to run based on cron schedules, and returns eligible (item_id, tenant_id) tuples. Includes safety logic to reclaim stale "running"/"queued" runs older than 60 minutes.

## What Was Implemented

### Files Changed
1. **core/tests/test_pipeline_repository.py**
   - Added datetime imports: `from datetime import datetime, timedelta, timezone`
   - Added config-related imports: `from app.configs import repository as configs_repo` and `from app.configs.schemas import BuilderConfig`
   - Added helper function: `_make_pipeline_config()` to create test pipeline configs
   - Added 6 new test functions testing various scenarios for `list_due_pipelines()`

2. **core/app/pipelines/repository.py**
   - Updated imports to include `timedelta` and `croniter`, plus `configs_repo`
   - Added reclaim constant: `_RUNNING_RECLAIM_MINUTES = 60`
   - Added function: `list_due_pipelines(session: Session) -> list[tuple[str, str]]`

### Implementation Details

The `list_due_pipelines()` function:
- Iterates over all pipeline configs via `configs_repo.list_configs_by_kind(session, kind="pipeline")`
- Filters out pipelines without refresh policies or with disabled policies
- For pipelines that have never run: marks them as due
- For pipelines with a latest run:
  - If status is "queued" or "running":
    - Reclaims (marks as due) if created_at is older than 60 minutes
    - Otherwise skips (in progress)
  - If status is final (succeeded/failed):
    - Uses croniter to calculate next scheduled tick from the run's created_at
    - Marks as due if next tick <= now
- Returns a list of (item_id, tenant_id) tuples for all due pipelines

## Testing Results

### TDD Verification

**Step 1: RED (tests fail)**
```
uv run pytest tests/test_pipeline_repository.py -v -k list_due_pipelines
```
Result: 6 tests FAILED with `AttributeError: module 'app.pipelines.repository' has no attribute 'list_due_pipelines'` (expected)

**Step 2: GREEN (tests pass)**
```
uv run pytest tests/test_pipeline_repository.py -v
```
Result: 17 tests PASSED (all existing + 6 new tests):
- test_create_run_defaults_to_queued PASSED
- test_get_run_round_trips PASSED
- test_get_run_scoped_to_tenant PASSED
- test_list_runs_ordered_most_recent_first PASSED
- test_mark_running_then_succeeded PASSED
- test_mark_failed_records_error PASSED
- test_append_node_stat_merges_into_existing_node_stats PASSED
- test_append_node_stat_scoped_to_tenant PASSED
- test_get_latest_run_returns_none_when_no_runs PASSED
- test_get_latest_run_returns_most_recent PASSED
- test_get_latest_run_scoped_to_tenant PASSED
- test_list_due_pipelines_excludes_pipelines_without_refresh_policy PASSED
- test_list_due_pipelines_excludes_disabled_policy PASSED
- test_list_due_pipelines_includes_never_run_enabled_pipeline PASSED
- test_list_due_pipelines_excludes_pipeline_not_yet_due PASSED
- test_list_due_pipelines_skips_run_already_in_progress PASSED
- test_list_due_pipelines_reclaims_stale_running_run PASSED

**Step 3: Lint-imports verification**
```
uv run lint-imports
```
Result: PASS — Contracts: 1 kept, 0 broken.

## Commit

```
20da2b2 feat(core): pipelines — list_due_pipelines (SP-15h)
```

## Self-Review Findings

- All 6 new test cases implemented exactly as specified in the brief
- All existing tests remain passing (no regressions)
- Import layering verified: `app.pipelines` importing `app.configs` is an allowed direction (consistent with `app.pipelines.jobs`)
- Exact code from brief was used (function signature, logic, constants)
- Code follows project conventions (French docstrings for complex logic, English function names)
- Timezone handling implemented correctly with fallback for naive datetimes
- Reclaim logic mirrors existing pattern from `app.harvest.repository.list_due_sources`
- croniter usage correctly integrated with datetime handling

## Issues & Concerns

None. Implementation is complete, tested, and verified per requirements.

## Fix: reclaim anchor (SP-15h review finding, 2026-08-07)

### Bug

`list_due_pipelines` measured staleness of a `"running"` run from `created_at`
(queue time, set once at `create_run` and never updated) instead of
`started_at` (set by `mark_running` when the run actually starts). A run that
sat `"queued"` for 55+ minutes then transitioned to `"running"` was
immediately reclaimed as "presumably stuck" on the next sweep tick, spawning
a duplicate concurrent run of the same pipeline.

### RED

Added `test_list_due_pipelines_does_not_reclaim_run_that_just_started_after_long_queue`
to `core/tests/test_pipeline_repository.py` (right after
`test_list_due_pipelines_reclaims_stale_running_run`): backdates `created_at`
by 61 minutes, then calls `mark_running` (fresh `started_at`), and asserts
`list_due_pipelines(s) == []`. Run before the fix:

```
FAILED tests/test_pipeline_repository.py::test_list_due_pipelines_does_not_reclaim_run_that_just_started_after_long_queue
AssertionError: assert [('9075ff8a...', 'default')] == []
```

Confirms the bug reproduces exactly as described.

### Fix

In `core/app/pipelines/repository.py`'s `list_due_pipelines`: for a `"running"`
run with a non-`None` `started_at`, the reclaim anchor is now `started_at`
(normalized to aware UTC, same pattern as the existing `created_at`
normalization) instead of `created_at`. `"queued"` runs still anchor on
`created_at` (no better timestamp exists before a run starts). The
`next_tick = croniter.croniter(policy.cron, created_at)...` line was left
untouched, as scoped.

### Deviation from the brief's stated scope — existing test had to change too

The brief asserted that `test_list_due_pipelines_reclaims_stale_running_run`
"exercises a run left in `running` with backdated `created_at` AND no fresh
`started_at` override" and would still pass unmodified under the fix. That
turned out to be factually wrong: that test calls `repo.mark_running(s,
run_id=run.id)` *before* backdating `created_at`, so `mark_running` sets
`started_at` to a fresh timestamp (now) that is never backdated. Running the
full suite after the fix confirmed this concretely:

```
FAILED tests/test_pipeline_repository.py::test_list_due_pipelines_reclaims_stale_running_run
assert repo.list_due_pipelines(s) == [(item_id, tenant.id)]
```

The test's scenario as written (old `created_at`, fresh `started_at`) is
*exactly* the "just started after a long queue" case the fix is meant to
protect — under the corrected anchor logic it must NOT be reclaimed, which
directly contradicts that test's own assertion. The test was implicitly
asserting the buggy behavior as correct.

Resolution applied (minimal, preserves the test's original intent of
verifying a genuinely-stuck running run gets reclaimed): backdated
`run.started_at` by 61 minutes as well as `run.created_at`, so the scenario
now represents a run that actually started running over an hour ago and
never finished — a real stuck run — rather than a run that merely waited a
long time in queue before just starting. Added a comment explaining why
backdating `created_at` alone is no longer sufficient post-fix, cross-
referencing the new regression test.

This was not pre-authorized in the brief's scope, but leaving the existing
test unmodified was not an option: it would either fail (contradicting "all
existing tests must pass") or, if left passing, would mean the fix wasn't
actually applied. Flagging this explicitly rather than silently editing
another task's test.

### GREEN — full `test_pipeline_repository.py` (18 tests)

```
tests/test_pipeline_repository.py::test_create_run_defaults_to_queued PASSED
tests/test_pipeline_repository.py::test_get_run_round_trips PASSED
tests/test_pipeline_repository.py::test_get_run_scoped_to_tenant PASSED
tests/test_pipeline_repository.py::test_list_runs_ordered_most_recent_first PASSED
tests/test_pipeline_repository.py::test_mark_running_then_succeeded PASSED
tests/test_pipeline_repository.py::test_mark_failed_records_error PASSED
tests/test_pipeline_repository.py::test_append_node_stat_merges_into_existing_node_stats PASSED
tests/test_pipeline_repository.py::test_append_node_stat_scoped_to_tenant PASSED
tests/test_pipeline_repository.py::test_get_latest_run_returns_none_when_no_runs PASSED
tests/test_pipeline_repository.py::test_get_latest_run_returns_most_recent PASSED
tests/test_pipeline_repository.py::test_get_latest_run_scoped_to_tenant PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_excludes_pipelines_without_refresh_policy PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_excludes_disabled_policy PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_includes_never_run_enabled_pipeline PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_excludes_pipeline_not_yet_due PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_skips_run_already_in_progress PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_reclaims_stale_running_run PASSED
tests/test_pipeline_repository.py::test_list_due_pipelines_does_not_reclaim_run_that_just_started_after_long_queue PASSED

18 passed in 0.80s
```

Also ran the wider pipelines suite for collateral regressions:
`uv run pytest tests/ -k pipeline -q` → `222 passed, 14 skipped, 1060 deselected`.

### lint-imports

```
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

No regression, as expected (fix touches no imports).
