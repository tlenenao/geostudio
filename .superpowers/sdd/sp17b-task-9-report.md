# Task 9 report — `app/reports/jobs.py` (trigger step)

## What I implemented

- `core/app/reports/jobs.py` (new module, trigger half only, exactly per the brief's Step 3):
  - `ReportTriggerError` — always caught inside the sweep, always turns into an
    `audit_log` row, never crashes the loop.
  - `_session_factory()` — same `DATABASE_URL` env-var pattern as
    `app.alerts.jobs`/`app.pipelines.jobs`.
  - `_owner_user(session, *, tenant_id, item_id) -> User` — resolves the
    report item's `owner_id` via a direct `Item` select, loads the `User`.
  - `_trigger_due_reports(session_factory) -> None` — for each `(item_id,
    tenant_id)` from `reports_repo.list_due_reports`: loads the report config,
    resolves the owner, re-verifies the owner can `read` both the target
    bookmark item and the app the bookmark points at (via
    `items_repo.get_access_facts` + `sharing.authorization.can`), encodes the
    bookmark's analytics context (`encode_analytics_context`), creates an
    `export_jobs` row (`export_repo.create_job`, `format="pdf"`,
    `page_id`/`ctx` from the bookmark), creates a `report_runs` row
    (`reports_repo.create_run`), writes a success audit entry, commits, then
    defers `render_export_task`. Any `ReportTriggerError` along that path is
    caught, logged, audited as a failure, committed, and the loop continues
    to the next due report. Ends with `export_repo.reclaim_stuck_jobs` +
    commit (same as the brief).
- `core/tests/test_report_jobs.py` (new, from the brief's Step 1), with the
  `share_item` import dropped as instructed by the brief's note (unused by
  either test body). `NotifyError` and `can` are kept as given in the
  brief — not flagged for removal, and there is no ruff/import-linter
  "unused import" gate configured anywhere in this repo (checked
  `core/pyproject.toml` and repo root: no `[tool.ruff]` section, no
  `.pre-commit-config.yaml`), so this is a purely stylistic non-issue, not a
  build-breaking one.

## What I tested and results (TDD evidence)

RED — before creating `jobs.py`:
```
$ uv run pytest tests/test_report_jobs.py -v
ImportError: cannot import name 'jobs' from 'app.reports'
Interrupted: 1 error during collection
```

GREEN — after creating `jobs.py`:
```
$ uv run pytest tests/test_report_jobs.py -v
tests/test_report_jobs.py::test_trigger_creates_export_job_and_report_run_for_due_report PASSED
tests/test_report_jobs.py::test_trigger_skips_report_and_audits_when_owner_lost_bookmark_access PASSED
2 passed in 1.18s
```

Regression check — full `report`/`export` test slice (121 tests, includes
`test_report_config_schema.py`, `test_report_ctx.py`, `test_report_models.py`,
`test_report_repository.py`, `test_report_validation.py`,
`test_export_tokens.py`, `test_features_export_routes.py`,
`test_harvest_dataset_arcgis_export_routes.py`, `test_pipeline_runtime.py`,
`test_read_only_mode.py`, etc.): **121 passed, 1366 deselected**.

Full-suite collection sanity check (`pytest --collect-only -q`): **1487 tests
collected**, no import errors anywhere else in the tree.

Also ran `uv run lint-imports`: **1 kept, 0 broken** (note: `app.reports` is
not yet listed in the `[tool.importlinter]` layered-architecture contract in
`core/pyproject.toml`, so this module isn't checked by that contract either
way — out of scope for this task, the brief didn't ask for a layers-contract
edit, and adding a new module there is presumably a different task's or a
follow-up's concern).

## Files changed

- `core/app/reports/jobs.py` (new, 105 lines)
- `core/tests/test_report_jobs.py` (new, 106 lines)

Commit: `b722862` — `feat(core): _trigger_due_reports — resolve owner, re-check access, create render (SP-17b)`

## Self-review findings

- `ReportTriggerError`, `_session_factory`, `_owner_user`, and
  `_trigger_due_reports` all implemented exactly as specified in the brief —
  no deviation from the Step 3 code.
- Permission is re-verified against the report's **owner** (via
  `_owner_user`), not against any "caller"/request-scoped user — matches the
  system-sweep design intent and is exercised by
  `test_trigger_skips_report_and_audits_when_owner_lost_bookmark_access`
  (bookmark owned by a different user, never shared with the report's owner
  → `can()` returns false → `ReportTriggerError` → audited failure, no
  `report_runs` row, nothing deferred).
- Both the success path and every `ReportTriggerError` failure path call
  `write_audit` before `session.commit()`; the failure branch is inside the
  per-item `try/except` so one bad report does not stop the loop from
  processing the next due report.
- Did not add the notify step or the `@app.periodic`/`@app.task`-decorated
  `sweep_report_schedules_task` — those are explicitly Task 10's job and are
  absent from this file. `is_read_only_mode` and `app` (the procrastinate
  App) are imported (per the brief's literal Step 3 code) but not yet
  referenced in this file's body — that's expected: Task 10 appends the
  periodic sweep entrypoint to this same file and will be the first
  consumer of both, exactly mirroring how `app.alerts.jobs` uses
  `is_read_only_mode` only in its own `sweep_alert_rules_task`, not in the
  per-rule evaluation function.
- Test file import list: dropped `share_item` per the brief's explicit note
  (unused by either test). Left `NotifyError`/`can` as given — the brief
  only called out `share_item` by name, and there is no lint gate in this
  repo that would flag them; pytest output itself is clean (2 passed, no
  warnings).

## Issues or concerns

None. No blockers, no ambiguity — all pre-verified imports/signatures in the
task description (`write_audit`, `is_read_only_mode`, `request_scoped_session`,
`get_config_by_item`/`ConfigRead.kind`, `get_access_facts`/`get_item`,
`Item`, `app.jobs.app`, `can`, `User`) matched the current codebase exactly,
confirmed by direct inspection before writing any code.

## Follow-up fix: owner-lost-app-access coverage (review finding)

**Finding addressed:** `_trigger_due_reports` re-verifies two separate
permission checks against the report's owner — (1) can the owner read the
bookmark, and (2) can the owner read the bookmark's target app. Only check
(1) had a negative test (`test_trigger_skips_report_and_audits_when_owner_lost_bookmark_access`).
Check (2) — same `can(session, user_id=owner.id, action="read", item=app_facts)`
pattern, hit when `bookmark.appId` fails the read check — was structurally
correct on inspection but had zero test coverage.

**Fix:** added
`test_trigger_skips_report_and_audits_when_owner_lost_app_access` to
`core/tests/test_report_jobs.py`. It mirrors the existing negative test's
shape but flips which relationship is broken:

- `app_item` owned by `other` (bob), never shared with `owner` (alice).
- `bookmark` owned by `owner` (alice) itself, referencing `app_item.id` — so
  the owner's bookmark-read check passes (item they own), and the flow
  reaches the second check, which fails on the app.
- Report owned by `owner`, referencing that bookmark.

Assertions: `deferred == []` (no `render_export_task.defer` call),
`reports_repo.get_latest_run(...)` is `None` (no `ReportRun` created) — same
shape as the sibling test. Additionally queries `AuditLog` (via
`select(AuditLog).where(AuditLog.action == "report.run", AuditLog.object_id
== report_id)`, following the existing convention in `test_alert_jobs.py`)
and asserts `payload["success"] is False` and `payload["error"] == "target
app not readable by report owner"` — this is what proves the test took the
second (`ReportTriggerError("target app not readable by report owner")`)
branch in `jobs.py` and not the first (`"bookmark not readable by report
owner"`) one that the sibling test already covers.

No changes to `core/app/reports/jobs.py` — implementation was already
correct, this is test-only.

**Imports added** to `core/tests/test_report_jobs.py`: `sqlalchemy.select`,
`app.audit.models.AuditLog` (both already used elsewhere in the test suite,
e.g. `test_alert_jobs.py`).

### Test run

```
$ cd core && uv run pytest tests/test_report_jobs.py -v
tests/test_report_jobs.py::test_trigger_creates_export_job_and_report_run_for_due_report PASSED [ 33%]
tests/test_report_jobs.py::test_trigger_skips_report_and_audits_when_owner_lost_bookmark_access PASSED [ 66%]
tests/test_report_jobs.py::test_trigger_skips_report_and_audits_when_owner_lost_app_access PASSED [100%]

3 passed in 2.13s
```

Commit: `test(core): cover owner-lost-app-access path in _trigger_due_reports (SP-17b review fix)`
