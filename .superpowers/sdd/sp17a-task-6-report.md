# SP-17a — Task 6 report: job procrastinate `render_export_task`

## What was implemented

- `core/app/export/jobs.py` (new): `render_export_task(job_id, tenant_id)` — a
  `@app.task(queue="export")` procrastinate task that reads an `export_jobs`
  row, mints a short-lived export token, launches headless Chromium via
  Playwright, navigates the shell's runtime page, waits for
  `[data-export-ready="true"]`, calls the pure `render_export()` (Task 5) to
  get PNG/PDF bytes, uploads to S3, and marks the job `done`/`error`.
  `_launch_and_navigate(url) -> RenderPage` is factored out as the sole
  Chromium-touching function, monkeypatchable in tests.
- `core/pyproject.toml`: added `playwright>=1.45` dependency (Step 1 of the
  brief, verbatim), plus a new `playwright` pytest marker registration
  (`[tool.pytest.ini_options] markers`) — required for the guarded Step 6
  test to be collectible/selectable.
- `core/tests/test_export_jobs.py` (new): the brief's 4 orchestration tests
  plus the guarded `@pytest.mark.playwright` real-browser test — with fixes
  described below.
- `core/uv.lock`: updated by `uv sync` (adds `playwright`, `pyee`).

## TDD evidence

RED: after writing the test file with the brief's literal Step 2 code,
`uv run pytest tests/test_export_jobs.py -v` failed at collection with
`ImportError: cannot import name 'jobs' from 'app.export'` (module didn't
exist yet) — confirmed before writing `app/export/jobs.py`.

GREEN: after implementing `app/export/jobs.py` per the brief's Step 4 code
verbatim, plus three test-file fixes (below), all 4 orchestration tests pass,
then the guarded Step 6 test also passes once Chromium was installed.

## Three real bugs found in the brief's literal code, fixed

1. **`CORE_EXPORT_TOKEN_SECRET` too short (test-only bug).** The brief's
   fixture used `"test-export-secret"` (18 bytes). This repo's
   `filterwarnings = ["error", ...]` (pyproject.toml) promotes PyJWT's
   `InsecureKeyLengthWarning` (HS256 keys <32 bytes) to a hard exception,
   which the task's broad `except Exception` then turned into a spurious
   `mark_error` — breaking the intended "happy path" test. Sibling tests
   (`test_export_tokens.py`, `test_auth_export_token.py`, Task 4) already
   worked around this with a ≥32-byte secret. Fixed by using
   `"test-export-secret-padding-01234"` (33 bytes), matching that established
   convention.

2. **Stale identity-map reads in test assertions (test-only bug).**
   `db_session`'s `session` (via `make_session_factory`, `expire_on_commit=False`)
   keeps the `job` object cached after `create_job()`. `export_repo.get_job()`'s
   `select()` does not overwrite an already-loaded identity-map object's
   attributes by default in SQLAlchemy — so `refreshed.status` kept reading
   back the stale in-memory `"pending"` regardless of what the task's
   separate internal session/connection actually wrote to the DB. All three
   assertions were false negatives against a correct implementation. Fixed by
   calling `session.expire_all()` before each `get_job()` verification read
   (same class of fix as the existing
   `test_pipeline_sweep.py::test_sweep_commits_run_before_deferring`, which
   solves cross-session visibility with a separate session).

3. **`_FakePage` missing `.context.browser.close()` (test-only, brief
   anticipated it).** The brief's own Step-4 note flagged this explicitly:
   "if a test fails on AttributeError at closing, adapt `_FakePage`... rather
   than removing the real close call." That's exactly what happened; fixed by
   adding `_FakeContext`/`_FakeBrowser` stand-ins.

## One real production bug found and fixed (not test-only)

**`_launch_and_navigate`'s `sync_playwright().start()` was never paired with
`.stop()`.** `render_export_task`'s cleanup only called
`browser_page.context.browser.close()`. Reading Playwright's
`PlaywrightContextManager` (`_context_manager.py`) confirmed: when no asyncio
loop is already running (true for a sync worker task), Playwright creates and
owns a *new* event loop plus a background dispatcher greenlet driving a Node
driver subprocess connection — none of which is torn down by
`browser.close()` alone; only `playwright.stop()` (`__exit__`) cancels the
tasks, shuts down async generators, and closes the owned loop.

I confirmed this empirically, not just by code reading: running the guarded
real-Chromium test together with unrelated async tests
(`tests/test_mcp_auth.py`, `tests/test_jobs_observability.py`) in the same
pytest session reliably broke them with `RuntimeError: Runner is closed`
(anyio's globally-cached test `Runner`, see `anyio/pytest_plugin.py`). With
`test_export_jobs.py` excluded, `uv run pytest -q` passed cleanly at 1303/137;
including it (pre-fix) dropped 6 unrelated tests. This is not just a test
artifact — in production, every single export job on a long-running
export-worker process would leak a Node driver subprocess + event loop,
since `render_export_task` runs indefinitely across many jobs in one process.

Fix: `_launch_and_navigate` stashes the driver handle as
`page._geostudio_playwright` (plain attribute assignment — Playwright's
generated `Page`/`Browser` classes have no `__slots__`), keeping the
function's declared return type exactly `RenderPage` (no signature change,
`_FakePage` unaffected via `getattr(..., None)`). `render_export_task`'s
`finally` block now calls `playwright_driver.stop()` after
`browser.close()` when that attribute is present. The guarded Step-6 test's
own manual cleanup was updated the same way. Re-ran the combined session
after the fix: `test_export_jobs.py` + `test_mcp_auth.py` +
`test_jobs_observability.py` → 11/11 passed; full suite → 1308 passed
(1303 + the 5 export tests), 137 skipped, 0 failed.

## Files changed

- `core/app/export/jobs.py` (new)
- `core/pyproject.toml` (playwright dependency + `playwright` pytest marker)
- `core/tests/test_export_jobs.py` (new)
- `core/uv.lock` (via `uv sync`)

## Self-review checklist

- All 4 orchestration tests pass and genuinely prove "never a zombie job":
  the navigation-failure test asserts `status == "error"` and
  `"navigation timeout" in error` after `_launch_and_navigate` raises
  `RuntimeError` mid-task — confirmed via a fresh read after
  `session.expire_all()` (see bug #2 above), not a stale cached object.
- `is_export_enabled()` guard correctly short-circuits before touching
  Playwright: `test_render_export_task_marks_error_when_export_disabled`
  never monkeypatches `_launch_and_navigate`, so if the guard didn't
  short-circuit it would hit the real (unpatched) Playwright path and either
  crash the test process or hang — it doesn't, and the job ends in `error`.
- `test_render_export_task_missing_job_is_a_noop`: no exception, no DB
  mutation beyond the fixture's own commit — true no-op.
- Full core suite green: `uv run pytest -q` → **1308 passed, 137 skipped, 0
  failed** (includes the guarded Playwright test, which ran for real in this
  environment — see below).
- Import-linter (`uv run lint-imports`) → 1 kept, 0 broken (note:
  `app.export` is not currently in the layered-architecture contract's layer
  list at all — pre-existing state from earlier tasks, out of this task's
  scope to add).

## `mint_export_token` KeyError-safety finding

Confirmed both by code reading and by an empirical check (unset
`CORE_EXPORT_TOKEN_SECRET` entirely, run `render_export_task` end-to-end
against a real sqlite DB): `_secret()` in `app/auth/export_tokens.py` raises
a raw `KeyError: 'CORE_EXPORT_TOKEN_SECRET'`, which propagates up through
`mint_export_token()` and is caught by `render_export_task`'s
`except Exception as exc:` — the job correctly ends with
`status="error"`, `error="'CORE_EXPORT_TOKEN_SECRET'"`. No crash, no zombie
job. **No extra fix needed** for this specific concern; the broad
`except Exception` at the task boundary is exactly the right place for this
class of misconfiguration in a background job (as opposed to Task 4's HTTP
request path, where a clean 401 would be needed instead — out of scope
here).

## Guarded Playwright test (Step 6) — exact outcome

- `uv run playwright install --with-deps chromium` **failed**: `sudo: A
  terminal is required to authenticate` / `Failed to install browsers` /
  `Error: Installation process exited with code: 1` — same class of
  environment constraint already documented for SP-15d's QGIS sidecar test
  (no interactive sudo available in this session).
- Fallback `uv run playwright install chromium` (binary only, no
  `--with-deps` OS package step) **succeeded** — downloaded Chrome for
  Testing + Chrome Headless Shell without needing root.
- With the binary present, `uv run pytest tests/test_export_jobs.py -v -m
  playwright` **PASSED** (1/1): real Chromium launched, navigated a local
  `http.server`-served page, waited for the `data-export-ready` attribute,
  and produced a non-empty screenshot.
- So: **PASSED**, via the binary-only install path rather than
  `--with-deps`. This environment apparently already carries enough system
  libraries for headless Chromium to run without the OS-package step that
  needs root. Worth noting for the Dockerfile export-worker (Task 13): that
  Dockerfile can and should still use `playwright install --with-deps
  chromium` since it runs as root during image build, so this local
  workaround is not something to propagate there.

## Concerns / notes for follow-on tasks

- `app.export` is absent from the import-linter layered-architecture
  contract in `core/pyproject.toml` (`[[tool.importlinter.contracts]]
  layers`). Not a regression from this task (it was already absent before
  Task 6, since Tasks 1–5 created `app/export/{models,repository,rendering}.py`
  without adding it), but worth flagging for whichever task closes out
  SP-17a's cleanup — every other domain module is listed there.
- The `_geostudio_playwright` attribute-stashing fix is a private-attribute
  workaround rather than a first-class API; if a future task refactors
  `_launch_and_navigate`'s signature (e.g. to return a small dataclass
  bundling `page` + `playwright` explicitly), that would be cleaner than the
  `getattr(..., None)` pattern used here — flagging for awareness, not
  blocking.

## Fix round 1 — launch-failure resource leak (code review Important)

### What changed and why

Code review on commit `95e5a4c` (this task) found an Important: `_launch_and_navigate`
had no internal `try`/`except`. If any step after `sync_playwright().start()` —
`chromium.launch()`, `browser.new_page()`, `page.goto()`, or
`page.wait_for_selector(..., timeout=30_000)` (the realistic case: the shell
page never sets `data-export-ready`) — raised, the exception propagated with
`browser_page` never assigned. The caller's cleanup (`browser.close()` +
`playwright_driver.stop()`) lives in a `finally` scoped around
`render_export(browser_page, ...)`, entirely *after*
`_launch_and_navigate` has already returned — so it never ran for a failure
inside `_launch_and_navigate` itself. Job status was still correct
(`mark_error` via the outer `except Exception`, confirmed not a zombie-job
bug), but the Playwright driver process and/or the Chromium browser process
that had already been created leaked — every time, on the single most
realistic failure mode this feature will hit in production (slow/broken
shell page, bad `SHELL_BASE_URL`, network hiccup).

The existing `test_render_export_task_marks_error_never_zombie_on_navigation_failure`
could not catch this: it monkeypatches `_launch_and_navigate` itself to raise,
so it never exercises the function's real internals — it only proves the
job-status contract.

Fix, in `core/app/export/jobs.py`:

- `_launch_and_navigate`'s body (`chromium.launch` → `new_page` → `goto` →
  `wait_for_selector`) is now wrapped in `try`/`except Exception`. On any
  failure: close the browser if it was already launched (`browser is not
  None`), then always `playwright.stop()` (nested `try`/`finally` so a
  `browser.close()` failure can't skip the driver stop), then re-raise. On
  the success path, behavior is unchanged — `page._geostudio_playwright =
  playwright` is stashed exactly as before, same return type, same signature.
- Reviewer's associated Minor, fixed as scoped (a few lines, same code
  already being touched): in `render_export_task`'s existing `finally` block
  (around `render_export(...)`), `browser_page.context.browser.close()` and
  `playwright_driver.stop()` were flat siblings in the same `finally` body —
  if `close()` itself raised, `stop()` was skipped, leaking the driver. Now
  nested: `close()` is in its own `try`, `stop()` in the matching `finally`,
  so it always runs regardless of whether `close()` raised.

Did not touch: `mark_error`, the outer `except Exception` in
`render_export_task`, or any job-status logic — out of scope per the review,
confirmed still correct (all pre-existing status tests still pass unchanged).

### Regression test

Added `test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure`
in `core/tests/test_export_jobs.py`. Unlike the existing navigation-failure
test, this one does **not** monkeypatch `_launch_and_navigate` away — it lets
the real function body run and only fakes the Playwright entry point
(`playwright.sync_api.sync_playwright`), returning a fake driver/chromium/
browser chain where `browser.new_page()` raises *after* the fake driver and
fake browser have already been "created" (mirrors: driver started, browser
launched, then a downstream step fails). Asserts `browser.closed is True` and
`driver.stopped is True` after the call raises — proving the leak is closed,
not just that the exception propagates.

**RED (before fix — jobs.py temporarily reverted via `git stash` to the
pre-fix state, test added on top):**

```
tests/test_export_jobs.py::test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure FAILED

>       assert browser.closed is True
E       assert False is True
E        +  where False = <tests.test_export_jobs._FakeLaunchedBrowser object at 0x7e00c6006660>.closed

1 failed, 5 deselected in 0.61s
```

**GREEN (after fix restored):**

```
tests/test_export_jobs.py::test_render_export_task_marks_done_on_success PASSED
tests/test_export_jobs.py::test_render_export_task_marks_error_when_export_disabled PASSED
tests/test_export_jobs.py::test_render_export_task_marks_error_never_zombie_on_navigation_failure PASSED
tests/test_export_jobs.py::test_render_export_task_missing_job_is_a_noop PASSED
tests/test_export_jobs.py::test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure PASSED
tests/test_export_jobs.py::test_launch_and_navigate_real_chromium_waits_for_export_ready PASSED

6 passed in 1.68s
```

(The guarded real-Chromium test ran and passed too — the binary installed in
this environment during Task 6 is still present.)

### Full suite regression check

`cd core && uv run pytest -q` after the fix:

```
1309 passed, 137 skipped in 87.42s (0:01:27)
```

(1308 at Task 6's own final check + 1 new regression test = 1309; 137 skipped
unchanged; 0 failed.) No regressions.

### Commit

`c994e94` — `fix(core): SP-17a — export_worker : fuite Chromium/driver sur
échec de lancement`. Files: `core/app/export/jobs.py`,
`core/tests/test_export_jobs.py`. (An unrelated pre-existing uncommitted
change to `.superpowers/sdd/progress.md`, present before this fix round
started, was deliberately left out of this commit — not part of this fix.)
