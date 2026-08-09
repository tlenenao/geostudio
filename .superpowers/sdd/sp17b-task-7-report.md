# Task 7 report — `app.reports.repository`

## What I implemented

`core/app/reports/repository.py`, verbatim per the brief's Step 3: CRUD
(`create_run`, `get_run`, `list_runs`, `get_latest_run`, `mark_notified`)
plus two cross-tenant sweep helpers (`list_unnotified_runs`,
`list_due_reports`) for later tasks' periodic sweep. `list_due_reports`
mirrors `app.pipelines.repository.list_due_pipelines`'s
croniter-against-last-`created_at` pattern, including the timezone-naive
`created_at` guard (SQLite round-trips datetime without tzinfo).

## TDD evidence

**RED**: wrote `core/tests/test_report_repository.py` (Step 1, verbatim)
first, ran `uv run pytest tests/test_report_repository.py -v` before
creating `repository.py`:

```
ImportError: cannot import name 'repository' from 'app.reports'
```

(the module didn't exist yet — equivalent failure to the brief's expected
`ModuleNotFoundError`, just surfaced as `ImportError` because
`app/reports/__init__.py` already existed as an empty package from Task 6).

**GREEN**: after implementing `repository.py`:

```
tests/test_report_repository.py::test_create_run_and_get_run_round_trip PASSED
tests/test_report_repository.py::test_list_runs_orders_most_recent_first PASSED
tests/test_report_repository.py::test_get_latest_run_returns_none_when_no_run_exists PASSED
tests/test_report_repository.py::test_mark_notified_sets_timestamp PASSED
tests/test_report_repository.py::test_list_unnotified_runs_excludes_already_notified PASSED
tests/test_report_repository.py::test_list_due_reports_returns_report_with_no_prior_run PASSED
tests/test_report_repository.py::test_list_due_reports_ignores_disabled_refresh_policy PASSED
tests/test_report_repository.py::test_list_due_reports_respects_cron_cadence_against_last_run PASSED

8 passed in 1.14s
```

## Files changed

- `core/app/reports/repository.py` (new)
- `core/tests/test_report_repository.py` (new)

Nothing else touched — no changes to `core/app/reports/models.py`, no
wiring into jobs/routes (out of scope, later tasks).

## Self-review findings

- **Test count discrepancy**: the task brief's prose (both in the plan
  excerpt and Step 4's "Expected: PASS (9 tests)") claims 9 tests, but the
  brief's own Step 1 code block only defines 8 `def test_...` functions. I
  transcribed Step 1 verbatim (confirmed by `grep -c "^def test_"` = 8) and
  did not invent a 9th test, since the brief states "the exact code to
  write" and the exact code has 8. Flagging this as a documentation
  inconsistency in the brief rather than a gap in my implementation — worth
  a look if a 9th test was intended (e.g. testing `list_runs` tenant
  isolation or `list_due_reports` respecting per-tenant scoping), but I
  didn't add one unprompted since the brief didn't specify what it would
  assert.
- All 7 functions named in the brief's Interfaces section are present:
  `create_run`, `get_run`, `list_runs`, `get_latest_run`, `mark_notified`,
  `list_unnotified_runs`, `list_due_reports`.
- Confirmed the timezone-naive `created_at` guard
  (`if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)`)
  is present in `list_due_reports`, matching the brief and the sibling
  pattern in `app.pipelines.repository`/`app.alerts.repository`.
- Verified `configs_repo.list_configs_by_kind` signature and return shape
  (`list[tuple[str, str, BuilderConfig]]` = `item_id, tenant_id, config`)
  against the actual source (`core/app/configs/repository.py:91`) before
  trusting the brief's assumption — matches exactly, cross-tenant scan by
  design, same discipline documented in its own docstring.
- Verified `ReportSchedulePayload` (`core/app/configs/schemas.py:316`) has
  `refreshPolicy: PipelineRefreshPolicy` (reused verbatim) and `channels`,
  matching the test fixture body and the repository's `payload.refreshPolicy`
  access.
- Test output is pristine — no warnings, no unrelated failures.
- Did not touch any file outside this task's scope; the other modified
  files visible in `git status` (`.superpowers/sdd/*.md`,
  `docs/superpowers/...`) are pre-existing changes from prior
  tasks/sessions, not staged or committed by me.

## Issues or concerns

None blocking. Only the test-count documentation mismatch noted above
(8 actual vs. 9 claimed in prose) — did not affect implementation
correctness, just flagging for whoever reviews the plan text.
