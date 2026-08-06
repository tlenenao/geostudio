# Task 3 report — REST connector materialization (`connector_runtime.py`)

## Summary

Implemented `core/app/pipelines/connector_runtime.py` with
`materialize_rest_connector()` and `ConnectorRuntimeError`, running a real
`dlt` pipeline (dlt 1.29.1, resolved from `dlt>=1.6`) against a scratch
DuckDB file, ATTACHing it read-only into the runtime's own DuckDB
connection, selecting `records` into a `TEMP TABLE` while dropping
`_dlt_id`/`_dlt_load_id`, then detaching and deleting the scratch
directory in `finally`. Auth is resolved from the SP-15e secrets store at
execution time via `app.secrets.repository.get_secret_payload`.

## Files changed

- `core/app/pipelines/connector_runtime.py` — new module.
- `core/tests/test_pipeline_connector_runtime.py` — new test file (9 tests).
- `core/pyproject.toml` — added `dlt>=1.6` to `dependencies`,
  `pytest-httpserver>=1.0` to `[dependency-groups] dev`.
- `core/uv.lock` — updated by `uv sync`.

Commit: `9b6d1df feat(core): pipelines — reader.connector.rest materialization (dlt REST client)`.

## TDD evidence

**RED** — before creating `connector_runtime.py`:

```
cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v
...
ImportError: cannot import name 'connector_runtime' from 'app.pipelines'
```

**GREEN** — after implementation:

```
cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v -s
...
9 passed in 2.88s
```

No warnings, no dlt telemetry chatter in output.

Full suite sanity check: `cd core && uv run pytest -q` → `1106 passed, 127
skipped` (all skips pre-existing postgis/qgis markers, no regressions).
Import-linter (`uv run lint-imports`): `1 kept, 0 broken` — `app.pipelines`
stays under `app.secrets` in the layer contract, no new violation.

## Deviations from the brief

The brief's code was written against dlt's public docs without running it;
I verified the actually-installed dlt 1.29.1's real API by introspecting
`inspect.signature(...)` on every class/function the brief imports before
writing the implementation. Findings:

1. **`RESTClient.__init__`, `dlt.pipeline`, `dlt.destinations.duckdb`,
   `APIKeyAuth`/`BearerTokenAuth`/`HttpBasicAuth`/`OAuth2ClientCredentials`,
   `PageNumberPaginator`/`OffsetPaginator`/`JSONResponseCursorPaginator`
   constructors** — all matched the brief's kwargs exactly in this dlt
   version. No signature changes needed for those.

2. **`_build_paginator("none", ...)`** — the brief returns `None` for
   `paginator=None` passed to `RESTClient`. In dlt 1.29.1 this triggers
   dlt's runtime auto-detection path on every `paginate()` call, which logs
   a `WARNING`-level message (`Fallback paginator used:
   SinglePagePaginator...`) to the `dlt` logger on every single-page fetch —
   this is real chatter that would show up in worker logs in production, not
   just test output. I changed `_build_paginator` to return an explicit
   `SinglePagePaginator()` instance instead of `None` for the `"none"` case
   (imported from `dlt.sources.helpers.rest_client.paginators`, already the
   same module the brief imports from). Behavior is unchanged — a single
   page fetched exactly once — the warning is what disappears.

3. **`PageNumberPaginator` `total_path`** — I passed `total_path=None`
   explicitly (brief didn't set it, so it would default to `"total"`).
   Harmless in practice for these tests since our REST responses are raw
   JSON arrays (no `"total"` key to match against), but explicit is safer
   given `paginator="page_number"` is documented (design §2) to work off
   `stop_after_empty_page` (default `True`) rather than a `total` count for
   the array-body case this connector targets.

4. **Test file `_create_secret` helper / `created_by="u1"`** — the brief's
   test code passes a literal string `"u1"` as `created_by`. This is a real
   bug in the brief, unrelated to dlt: `ConnectorSecret.created_by` is a
   genuine SQLAlchemy `ForeignKey("users.id")` (see
   `core/app/secrets/models.py:23`), and `"u1"` is not a real user id — this
   raised `sqlite3.IntegrityError: FOREIGN KEY constraint failed` in the 4
   tests that create a secret, independent of anything dlt-related. I
   added a `user` fixture (mirroring the pattern already used in
   `tests/test_secrets_repository.py`'s `tenant_and_user` fixture) that
   creates a real user via `app.users.repository.get_or_create_user`, and
   threaded `user.id` through `_create_secret` and the 4 affected test
   signatures (`test_materialize_rest_connector_injects_bearer_token`,
   `_injects_api_key_query_param`, `_injects_basic_auth`,
   `_wrong_secret_kind_raises`). No behavior under test changed — only the
   test fixture's foreign key satisfied.

Everything else (helper structure `_qi`/`_resolve_secret`/`_build_auth`/
`_build_paginator`/`_run_dlt_and_attach`/`materialize_rest_connector`,
`ConnectorRuntimeError` message strings, telemetry env var set before
`import dlt`, guarded session passed into `RESTClient`, plumbing-column
exclusion) matches the brief's Step 4 code verbatim.

## Self-review checklist

- Unauthenticated GET: covered, passes.
- `recordsPath` extraction (`data.items`): covered via `data_selector`,
  passes.
- All 3 REST-relevant secret kinds (bearer/api_key/basic_auth) inject real
  auth verified by the test HTTP server (header match / query_string match
  / `Authorization: Basic ...` prefix check): all 3 pass.
- `page_number` pagination terminating on empty page: passes (3rd page
  returns `[]`, `stop_after_empty_page=True` default stops the loop).
- Wrong-secret-kind (`postgres_dsn` used for a REST connector) raises
  `ConnectorRuntimeError` matching `"not usable by reader.connector.rest"`:
  passes.
- Missing secret raises `ConnectorRuntimeError` matching `"not found"`:
  passes.
- `_dlt_id`/`_dlt_load_id` excluded from the final `TEMP TABLE` (`cols ==
  {"id", "name"}` exactly): passes.
- Scratch directory (destination DB file + dlt's `pipelines_dir`) cleaned
  up in `finally` via `shutil.rmtree(scratch_dir, ignore_errors=True)` in
  `_run_dlt_and_attach` — both live under the same `scratch_dir`, one
  `rmtree` gets both. `ATTACH`/`DETACH` also wrapped so a failure mid-select
  still detaches before the outer `finally` deletes the files.
- `os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")` is the
  first statement after `import os`, strictly before `import dlt` — matches
  brief and matches SP-15f's stated global constraint.
- Guarded `requests.Session` from Task 2 (`build_guarded_session()`) is
  passed as `session=` into `RESTClient(...)` — real SSRF protection wired
  through, not bypassed. Confirmed by the `_no_ssrf_guard` autouse fixture
  in the test file, which patches `pipelines_egress.assert_egress_allowed`
  specifically (not the session-building or header/auth injection paths) —
  if the guard weren't actually wired into the request path, patching it
  would have no observable effect either way, so this only proves the
  tests aren't blocked by it, not that the guard is wired. I additionally
  confirmed by reading `egress.py`: `build_guarded_session()` mounts a
  `_GuardedHTTPAdapter` on both `http://`/`https://` that calls
  `assert_egress_allowed(request.url)` in `send()` — this is the actual
  requests-level hook, and it is the same session instance passed into
  `RESTClient(session=...)`, which dlt's REST client uses for all its HTTP
  calls (verified by reading dlt's installed `RESTClient` — it stores and
  reuses the passed `session` rather than constructing its own).
- Test output is pristine: no stray warnings, no dlt telemetry log lines
  (fixed by using `SinglePagePaginator()` explicitly instead of relying on
  dlt's auto-detection for `paginator="none"`, see Deviation #2 above).

## Concerns

- None blocking. The one non-brief judgment call with any user-visible
  effect is the `SinglePagePaginator()` swap (Deviation #2) — pure noise
  reduction, no behavior change, kept minimal.
- Task 4 (Postgres half) will add `materialize_postgres_connector` to this
  same file; nothing in this task's structure should need revisiting for
  that (the `_qi`/`ConnectorRuntimeError`/`_resolve_secret` helpers are
  already reusable as-is per the brief's own note in `ConnectorRuntimeError`'s
  docstring).

---

## Fix report — SSRF guard bypass on OAuth2 token exchange (review finding on 9b6d1df)

**Finding**: In `_build_auth()` (`core/app/pipelines/connector_runtime.py`), the
`oauth2_client_credentials` branch built `OAuth2ClientCredentials(access_token_url=...,
client_id=..., client_secret=...)` without a `session=`. dlt's `OAuth2ClientCredentials`
(`dlt.sources.helpers.rest_client.auth`) falls back to `dlt.sources.helpers.requests.client.session`
(its own default, unguarded session) whenever `self.session` is `None`, and
`obtain_token()` does `self.session.post(self.access_token_url, ...)` directly — this
POST never went through `app.pipelines.egress.build_guarded_session()`'s
`_GuardedHTTPAdapter`, so a secret with a `tokenUrl` pointing at an internal/forbidden
host would bypass `assert_egress_allowed` entirely. Verified independently by reading
the installed dlt source (`inspect.getsource(OAuth2ClientCredentials)`): confirmed
`session: Annotated[BaseSession, NotResolved()] = None` field, `__post_init__` default-session
fallback, and `obtain_token()`'s direct `self.session.post(...)` call — matches the
finding exactly. The other three secret kinds (`bearer_token`, `api_key`, `basic_auth`)
only add headers/query params to the caller-supplied (already-guarded) session and make
no request of their own, so they were never affected.

**Fix**: passed `session=build_guarded_session()` into the `OAuth2ClientCredentials(...)`
constructor in `_build_auth()`, reusing the module's existing `build_guarded_session`
import (already used once per `materialize_rest_connector()` call for the `RESTClient`'s
own session — confirmed cheap/side-effect-free to call twice: `requests.Session()` +
mounting two adapters, no I/O).

**Regression test added**: `test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard`
in `core/tests/test_pipeline_connector_runtime.py`. Creates an `oauth2_client_credentials`
secret with `tokenUrl="http://127.0.0.1:1/oauth/token"` (loopback, blocked by the real
guard) and asserts the SSRF guard fires. Two things had to be handled beyond the literal
brief:

1. The file's autouse fixture `_no_ssrf_guard` monkeypatches
   `pipelines_egress.assert_egress_allowed` to a no-op for every other test in the file
   (they exercise the connector, not the guard). This test needs the REAL guard, so it
   captures the real function at module-import time (`_REAL_ASSERT_EGRESS_ALLOWED =
   pipelines_egress.assert_egress_allowed`, evaluated before the autouse fixture ever
   runs) and re-installs it via `monkeypatch.setattr` inside the test body — restored
   automatically by pytest's monkeypatch teardown.
2. Empirically (verified by a standalone repro script, not from docs), dlt does not let
   the `EgressBlockedError` raised inside the `_records` generator (via
   `auth.__call__()` → `obtain_token()` → guarded session's adapter) propagate directly:
   it wraps it in `dlt.extract.exceptions.ResourceExtractionError`, itself wrapped in
   `dlt.pipeline.exceptions.PipelineStepFailed` (both `raise ... from exc`, so the
   `__cause__` chain is intact: `PipelineStepFailed.__cause__` →
   `ResourceExtractionError.__cause__` → `EgressBlockedError`). The test therefore walks
   `__cause__` looking for `EgressBlockedError` rather than asserting on the outermost
   exception type directly — this is the correct way to assert "the guard fired, not
   some unrelated dlt/network error", matching the finding's intent.

**Covering test command**:
```
cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v
```
Result: **10 passed** (9 pre-existing + 1 new), 2.97s.

```
cd core && uv run pytest tests/test_pipeline_egress.py -v
```
Result: **14 passed**, no regression, 0.06s.

**Files changed**:
- `core/app/pipelines/connector_runtime.py` — `_build_auth()`, added `session=build_guarded_session()`.
- `core/tests/test_pipeline_connector_runtime.py` — added `_REAL_ASSERT_EGRESS_ALLOWED` module-level
  capture + new regression test.

**Concerns**: none blocking. The wrapped-exception behavior (dlt swallowing/re-wrapping
generator exceptions) is worth keeping in mind if `materialize_rest_connector` ever grows
its own error-translation layer (e.g. into `ConnectorRuntimeError`) — right now no such
translation exists for network/extraction errors (only for the pre-flight
`_resolve_secret`/`_build_auth` validation errors), so callers of this function need to be
aware that `EgressBlockedError` currently arrives wrapped, not bare.
