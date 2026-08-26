# Task 3 report — Format d'erreur unique RFC 7807 (3.5a)

## Summary

Implemented all 12 steps of the brief. Every HTTP error response from the
core API now goes through three global exception handlers registered on
`create_app()`'s `FastAPI` instance (`ValidationHTTPException`,
`HTTPException`, `Exception`), all emitting
`application/problem+json` with `{type, title, status, detail}` at the top
level. Structured validation errors (`_validation_error` in
`features/routes.py`, plus the 6 inline ArcGIS-connector sites in
`harvest/routes.py`) now raise the new `ValidationHTTPException`
(`core/app/errors.py`), whose `errors` list is exposed as a **top-level**
`errors` extension member — never nested under `detail`, which stays a
plain string everywhere, including for the generic `Exception`/plain
`HTTPException` paths.

Commit: `2dafc5b feat(core): format d'erreur RFC 7807 unique sur toute l'API`

## Files changed

- `core/app/errors.py` (new) — `ValidationHTTPException(errors, status_code=400)`,
  intentionally left OUTSIDE `core/pyproject.toml`'s import-linter
  `layers` (verified: `pyproject.toml` diff is empty), same precedent as
  `app.db`/`app.observability`.
- `core/app/main.py` — 3 exception handlers registered right after
  `observability.instrument_app(app)`, before `read_only_guard`. Used the
  Step 4b fallback form (stdlib `logging`, not
  `observability.record_unhandled_exception`) — verified first via
  `grep -n "def record_unhandled_exception\|def.*exception" app/observability.py`,
  which matched nothing.
- `core/app/features/routes.py` — `_validation_error` now returns
  `ValidationHTTPException(errors=errors, status_code=status)`; import
  added. The other ~8 plain `HTTPException(...)` call sites in this file
  (string `detail`) are untouched, as specified.
- `core/app/harvest/routes.py` — all 6 inline
  `HTTPException(status_code=400, detail={"errors": [...]})` sites
  converted to `ValidationHTTPException(errors=[...], status_code=400)`,
  each site's exact `errors` content preserved individually (2×
  `invalid_filter`, 2× `invalid_aggregate`, 2× `unsupported_format` — the
  brief's warning that shapes differ site-to-site was checked; only the
  labels/exception attributes differ, content preserved verbatim). Import
  added; the plain `HTTPException` import stays (23 other call sites still
  use it with string `detail`, confirmed via
  `grep -c "raise HTTPException("` = 23 before/after vs. 6 new
  `ValidationHTTPException(` sites).
- `core/tests/test_error_format.py` (new) — the brief's 3 tests, with two
  necessary fixes described below (RED→GREEN evidence below).
- `core/tests/test_features_routes_write.py` — 1 assertion updated
  (`["detail"]["errors"]` → `["errors"]"`), as the brief anticipated.
- `core/tests/test_features_routes_read.py` — **2 more assertions updated**
  (not named in the brief's Step 7 grep scope, which only covered
  `test_features_routes_write.py`/`test_harvest_*.py`). Found only by
  running the *full* suite in Step 11: `test_filters_forwarded_and_unknown_is_400`
  and `test_geom_intersects_parsing` also assert on `_validation_error`'s
  old nested shape via `FilterError`/geom-intersects parsing paths in
  `features/routes.py` that aren't `_validation_error`'s 11 named call
  sites in `harvest`/`features` write paths but the same helper. Both
  fixed with the same `["detail"]["errors"]` → `["errors"]` change.
- `shell/src/api/itemClient.ts` — both call sites
  (`requestFeatureWrite`, `requestAnalyticsSql`) updated exactly per the
  brief; the generic `!res.ok` branch (string `detail`) untouched.
- `shell/src/api/itemClient.test.ts` — 2 mock fixtures updated from
  `{ detail: { errors: [...] } }` to `{ errors: [...] }`.
- `shell/src/pages/SqlLabPage.test.tsx` — **1 more fixture updated**, not
  named in the brief (only `itemClient.test.ts` was named). This is a
  downstream consumer test of `requestAnalyticsSql`'s wire format that
  used the old nested shape; without this fix it would have regressed
  `npx vitest run`'s full-suite count. Fixed with the same pattern.
- `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` —
  regenerated per Step 10's exact CI incantation. **Diff is empty** — see
  "Deviation from the brief" below.

## TDD evidence (RED → GREEN)

RED (`uv run pytest tests/test_error_format.py -v`, before any
implementation): all 3 tests failed — `test_unhandled_exception_returns_problem_json`
on `assert response.status_code == 500` (`404 == 500`, see deviation #1
below before the test was corrected), and after correcting the test
itself, all 3 failed purely on the expected assertions (wrong
content-type / missing top-level `errors`), confirming the RED state was
for the right reason, not a broken test:

```
tests/test_error_format.py::test_unhandled_exception_returns_problem_json FAILED
  AssertionError: assert 'text/plain; charset=utf-8' == 'application/problem+json'
tests/test_error_format.py::test_plain_http_exception_returns_problem_json FAILED
  AssertionError: assert 'application/json' == 'application/problem+json'
tests/test_error_format.py::test_validation_exception_carries_top_level_errors FAILED
  AssertionError: assert 'application/json' == 'application/problem+json'
```

GREEN (after `errors.py` + `main.py` handlers + `_validation_error`
conversion):

```
tests/test_error_format.py::test_unhandled_exception_returns_problem_json PASSED
tests/test_error_format.py::test_plain_http_exception_returns_problem_json PASSED
tests/test_error_format.py::test_validation_exception_carries_top_level_errors PASSED
```

## Deviations from the brief's literal text (verified, not guessed)

1. **`test_unhandled_exception_returns_problem_json` couldn't reach the new
   route as written.** `create_app()` ends with
   `app.mount("/", mcp_server.streamable_http_app())` — a `Mount` at the
   root path, which Starlette matches as `Match.FULL` for *any* path
   prefix. The brief's test registers `@app.get("/__boom")` *after*
   `create_app()` returns, which appends the route to
   `app.router.routes` *after* that mount — so the mount intercepts the
   request first and the sub-app 404s (`text/plain`), never reaching
   `boom()`. Fixed by moving the newly-added route to the front of
   `app.router.routes` (`app.router.routes.insert(0, app.router.routes.pop())`)
   right after registering it, with a comment explaining why. Verified
   this reaches a real 500 from the raised `ValueError`.
2. **`test_validation_exception_carries_top_level_errors` needed an
   `Authorization: Bearer ...` header.** `/analytics/sql` depends on
   `get_current_user` (not `_optional`), which 401s on a missing Bearer
   prefix regardless of `CORE_AUTH_MODE=mock` (mock mode only skips JWKS
   verification of the token's *content*, not the header's presence).
   Added `headers={"Authorization": "Bearer mock"}`.
3. **Same test needed `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`
   env vars.** `get_duckdb_connection_factory` (used by `/analytics/sql`,
   no `dependency_overrides` in this plain-`create_app()` test) reads
   these three via `os.environ[...]` with no defaults, unlike
   `get_analytics_base_uri()`. Verified `open_connection()` only
   configures DuckDB settings in-process — no real network call happens
   before the SQL sandbox rejects the invalid SQL — so fake local values
   are safe. Added the 3 `monkeypatch.setenv` calls with a comment.

   None of these three change the *meaning* of the brief's tests (500 for
   unhandled exceptions, 400+top-level-errors for SQL validation, plain
   string `detail` for a generic 404) — they only make the test's HTTP
   request actually reach the code path the brief intended to exercise.

4. **Step 10's expected non-empty OpenAPI/TS diff turned out empty.**
   Verified by actually regenerating (`export_openapi.py` +
   `npm run gen:api-types`) and diffing: `git diff --stat -- core/openapi.json
   shell/src/api/generated/core-schema.d.ts` produced zero output, and
   `git status --short` on both files showed nothing. This is correct, not
   a bug: FastAPI derives the OpenAPI schema from route signatures /
   declared `responses=` — not from `@app.exception_handler(...)`
   registrations. None of the routes touched in this task declare an
   explicit `responses={400: ...}` referencing the old
   `{"detail": {"errors": [...]}}` shape, so the documented schema never
   encoded either the old or the new error format for any route — there
   was nothing to change. Both files are unmodified in the working tree
   (confirmed via `git status --short`), so nothing was staged/committed
   for them, correctly reflecting reality.
5. **2 additional stale-fixture fixes beyond the brief's named files**
   (`core/tests/test_features_routes_read.py`, 2 assertions;
   `shell/src/pages/SqlLabPage.test.tsx`, 1 fixture) — found only by
   running the *full* suite (Step 11), not the brief's Step 7/9 grep
   scope. Both are direct, unavoidable consequences of the documented
   breaking change (the same `_validation_error`/`requestAnalyticsSql`
   wire format everywhere), not scope creep — leaving them unfixed would
   have left the full suite red, contradicting Step 11's explicit
   "no regressions" requirement.

## Full-suite run (Step 11)

### Core (with `CORE_TEST_DATABASE_URL=postgresql://gis:gis@localhost:5433/gis_test`)

```
uv run pytest -q
...
FAILED tests/test_features_rls.py::test_scope_preserves_original_sql_error - ...
1 failed, 1883 passed, 5 skipped in 181.60s
```

The **only** failure is the pre-existing, unrelated
`test_scope_preserves_original_sql_error` flagged in the task context
(confirmed pre-existing before Task 3 — the baseline was "1880 passed, 5
skipped, 1 pre-existing failure"; Task 3 adds 3 new tests in
`test_error_format.py`, so 1880 + 3 = 1883, matching exactly). Did not
touch it, per instructions.

```
uv run ruff check .        → All checks passed!
uv run ruff format --check . → 499 files already formatted
uv run mypy --strict app/auth app/secrets app/analytics app/copilot → Success: no issues found in 21 source files
uv run lint-imports         → Contracts: 1 kept, 0 broken. (app.errors confirmed NOT in the layer contract)
```

Also ran (not required by Step 11 but directly exercises the converted
harvest sites, for extra confidence):
`tests/test_harvest_dataset_arcgis_routes.py tests/test_harvest_dataset_arcgis_export_routes.py tests/test_harvest_arcgis_integration.py`
→ 26 passed.

### Shell

```
npx vitest run
 Test Files  161 passed (161)
      Tests  1461 passed (1461)
```

Matches the Global Constraints baseline exactly (161 files / 1461 tests —
no new tests added, only fixture edits in place).

```
npm run lint          → eslint . (clean)
npm run format:check  → All matched files use Prettier code style!
npm run build         → tsc --noEmit && vite build (succeeds; pre-existing
                         chunk-size warnings unrelated to this change)
```

## OpenAPI/TS diff summary

Empty — see deviation #4 above. Confirmed both `core/openapi.json` and
`shell/src/api/generated/core-schema.d.ts` are byte-identical to what was
already committed after actually running the regeneration commands (not
skipped).

## Self-review

**Completeness**
- All 3 new tests pass (after the 3 necessary test-harness fixes, none of
  which change the tests' intent).
- `_validation_error` and all 6 harvest sites converted — verified via
  `grep -c "raise HTTPException("` = 23 (unchanged plain sites) vs.
  `grep -c "ValidationHTTPException("` = 6 in `harvest/routes.py`, and
  `grep -n '"errors":' app/harvest/routes.py` returns nothing (no more
  nested-shape literals left).
- Both shell call sites updated exactly per the brief; the generic
  `!res.ok` branch (string `detail`) left untouched as instructed.
- OpenAPI+TS regeneration commands were run for real (not skipped); diff
  is legitimately empty, explained above — not "not regenerated", the 4th
  time this class of oversight is called out in the project history.
- Full suite green on both sides, only the pre-known pre-existing RLS
  failure as the sole exception.

**Quality**
- `detail` is always a plain string across all 3 handlers: the
  `ValidationHTTPException` handler passes through `exc.detail`, which is
  hardcoded to `"validation failed"` in `errors.py`'s `__init__`; the
  plain `HTTPException` handler coerces any non-string `detail` to
  `"request failed"`; the `Exception` handler hardcodes `"internal server
  error"`.
- `errors` only appears as a top-level RFC 7807 extension member, never
  nested under `detail` — verified both by the new test
  (`assert "errors" not in body` on the plain-exception path) and by
  reading every converted call site.
- The `Exception` handler never leaks the internal exception message —
  verified by the test's `assert "kaboom" not in response.text`.

**Discipline / scope**
- No other error sites were touched beyond what's named in the brief plus
  the 3 unavoidable downstream test-fixture fixes described in deviation
  #5.
- Found (via `grep -rn 'detail={"errors"' app/`) one more site with the
  old nested shape: `core/app/appexport/miniserver/main.py:173`. This is
  the SP-18c **standalone export mini-server** — a completely separate
  FastAPI app bundled into its own Docker image
  (`geostudio-appexport-standalone`), unrelated to `core/app/main.py`'s
  `create_app()` and not named anywhere in the brief. Left untouched, per
  "no scope creep" — flagging it here for a future task if RFC 7807
  standardization is meant to extend there too.
- `core/pyproject.toml`'s `[tool.importlinter]` `layers` list is
  unchanged (`git diff core/pyproject.toml` empty), confirming
  `app.errors` was correctly kept outside the layer contract as
  instructed.

## Issues / concerns

None blocking. Two points worth the next session's attention:
1. The empty OpenAPI/TS diff (deviation #4) is a genuine, verified fact
   about how FastAPI handles exception handlers vs. schema generation —
   not a shortcut. Flagging clearly in case a future task expects routes
   to declare explicit `responses={400: {"model": ...}}` blocks to make
   error shapes show up in the generated docs (out of this task's scope).
2. `app/appexport/miniserver/main.py`'s inline nested-shape site (noted
   above) is a pre-existing inconsistency with the rest of the API's now-
   unified error format, scoped to the standalone-export bundle. Left as
   a follow-up candidate, not fixed here.
