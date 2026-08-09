# Task 4 report — `render_export_task` builds the URL with `page_id`/`ctx`

## What I implemented

- `core/app/export/jobs.py`: `render_export_task` now captures `job.page_id`/`job.ctx`
  alongside the existing `item_id`/`user_id`/`export_format` unpack, and the URL-building
  block appends `/{quote(page_id, safe='')}` after the item id when `page_id` is set, and
  `&ctx={ctx}` at the end when `ctx` is set — applied exactly as given in the brief's Step 3
  (including the `from urllib.parse import quote` placed locally inside the function body,
  matching the brief's literal snippet).
- `core/tests/test_export_jobs.py`: added two tests, reusing this file's real fixtures —
  `db_session` (fixture returning `session, tenant, user, item`, not the brief's illustrative
  bare `session`/`tenant_id`/`item_id`/`user_id` names), `_FakePage` (existing fake page
  helper, unchanged), and the file's existing pattern of `monkeypatch.setattr(export_jobs,
  "_launch_and_navigate", ...)`.
  - `test_render_export_task_builds_url_with_page_id_and_ctx`
  - `test_render_export_task_url_unchanged_when_page_id_and_ctx_absent`

### One real adaptation beyond fixture naming

The brief's illustrative snippet asserts `/apps/{item_id}/page-2?exportToken=`. This file's
`db_session` fixture creates an item with `resource_type="map"` and a `BuilderConfig(kind="map",
...)`. `render_export_task` derives `route = "maps" if config.kind == "map" else "apps"`, so
with this fixture the route is always `"maps"`, not `"apps"`. I adjusted both new tests'
assertions to `/maps/{item.id}/page-2?exportToken=` and `/maps/{item.id}?exportToken=`
accordingly — asserting against what this fixture actually produces rather than the brief's
generic illustrative path.

## TDD evidence

**RED** — ran `uv run pytest tests/test_export_jobs.py -k "page_id_and_ctx" -v` before the
`jobs.py` change:
- `test_render_export_task_builds_url_with_page_id_and_ctx` — FAILED with
  `AssertionError: assert '/maps/<id>/page-2?exportToken=' in 'http://shell.test/maps/<id>?exportToken=...'`
  — exactly the expected failure (no `/page-2` segment yet).
- `test_render_export_task_url_unchanged_when_page_id_and_ctx_absent` — PASSED already (expected:
  this test only asserts the no-op path, which required no code change).

**GREEN** — after applying the brief's Step 3 change, ran
`cd core && uv run pytest tests/test_export_jobs.py -v`:

```
tests/test_export_jobs.py::test_render_export_task_marks_done_on_success PASSED
tests/test_export_jobs.py::test_render_export_task_marks_error_when_export_disabled PASSED
tests/test_export_jobs.py::test_render_export_task_marks_error_never_zombie_on_navigation_failure PASSED
tests/test_export_jobs.py::test_render_export_task_builds_url_with_page_id_and_ctx PASSED
tests/test_export_jobs.py::test_render_export_task_url_unchanged_when_page_id_and_ctx_absent PASSED
tests/test_export_jobs.py::test_render_export_task_missing_job_is_a_noop PASSED
tests/test_export_jobs.py::test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure PASSED
tests/test_export_jobs.py::test_launch_and_navigate_real_chromium_waits_for_export_ready PASSED

8 passed in 17.53s
```

All 8 tests pass, including the real-Chromium `@pytest.mark.playwright` test (Chromium was
available in this environment, so it ran for real rather than skipping).

## Files changed

- `core/app/export/jobs.py`
- `core/tests/test_export_jobs.py`

Diff confirmed via `git diff` before commit — only these two files touched, no unrelated changes.

## Self-review

- Both new test cases implemented (present case + unchanged/absent case). ✓
- `page_id` is `quote()`-d with `safe=''` before being inserted into the URL path, exactly per
  the brief. ✓
- Test output is pristine (no warnings/errors in the 8-test run above). ✓
- Ran `ruff check` on both changed files as an extra check: found 3 pre-existing issues (an E501
  long-line + an unused `generate_presigned_get_url` import at `jobs.py:16`, and an RUF059 unused
  `session` var at `test_export_jobs.py:216`) — all pre-existing, unrelated to my diff (confirmed
  by line numbers falling outside the changed hunks, and by `git diff` showing only the intended
  edits). Did not touch them, per the instruction to only touch this task's target code.
- No changes outside `jobs.py` and its test file. ✓

## Issues or concerns

None. The brief's Step 3 code matched the current file exactly as promised, and the only
adaptation needed was the `apps`→`maps` route correction driven by this file's actual fixture,
which is a faithful application of the brief's own instruction to adapt to the file's real
conventions rather than invent new ones.
