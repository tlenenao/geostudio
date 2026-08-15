# Task 5 report — narrow, capability-gated CORS middleware (SP-18b)

## What was implemented

Added a narrow, purpose-built CORS middleware to `core/app/main.py`, gated
behind `CORE_APPEXPORT_ENABLED`, so that the SP-18b "Connecté" export bundle
(running client-side on a foreign origin, Task 7) can call the live core's
already-anonymous-capable read endpoints directly from the browser.

Three edits, exactly per brief:

1. Import line: `from fastapi.responses import JSONResponse` →
   `from fastapi.responses import JSONResponse, Response`.
2. New module-level regex `_APPEXPORT_CORS_PATH_RE`, directly below the
   existing `_EXPORT_PATH_RE`, matching the fixed allowlist: `/collections`,
   `/collections/{id}`, `/collections/{id}/schema`,
   `/collections/{id}/items`, `/collections/{id}/items/{fid}`,
   `/collections/{id}/aggregate`, `/extensions`.
3. New `appexport_cors` middleware inside `create_app()`, added directly
   after `read_only_guard`'s definition and before `get_session()`'s
   definition, guarded by `if is_appexport_enabled():` (evaluated once at
   `create_app()` time, same convention as the existing
   `if is_appexport_enabled(): app.include_router(appexport_routes.router)`
   further down — not re-checked per request). Behavior:
   - Non-matching path → passthrough, untouched (`call_next` only).
   - Matching path + `OPTIONS` → `204` with
     `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET,
     POST, OPTIONS`, `Access-Control-Allow-Headers: Content-Type`.
   - Matching path + any other method → normal response with
     `Access-Control-Allow-Origin: *` added.
   - When the flag is off, the middleware is never registered at all — zero
     per-request overhead and zero behavior change on any path.

Created `core/tests/test_appexport_cors.py` exactly as specified in the
brief (4 tests: header present on matched path when enabled, header absent
when disabled, preflight 204 with headers on matched path when enabled,
header absent on unmatched path even when enabled).

## TDD evidence

### RED (before the main.py changes)

```
tests/test_appexport_cors.py::test_cors_header_present_on_matched_path_when_enabled FAILED
tests/test_appexport_cors.py::test_cors_header_absent_when_disabled PASSED
tests/test_appexport_cors.py::test_cors_preflight_responds_on_matched_path_when_enabled FAILED
tests/test_appexport_cors.py::test_cors_header_absent_on_unmatched_path_when_enabled PASSED

FAILED test_cors_header_present_on_matched_path_when_enabled
  AssertionError: assert None == '*'
FAILED test_cors_preflight_responds_on_matched_path_when_enabled
  assert 404 == 204   # (brief predicted 405; actual FastAPI default for an
                       # unregistered OPTIONS route on this app is 404 — same
                       # failure signal, no OPTIONS handler exists yet)

2 failed, 2 passed in 2.41s
```

This matches the brief's expectation: the two "enabled" tests fail (no
header / wrong status for preflight), the two "disabled"/"unmatched" tests
already pass (nothing to regress).

### GREEN (after the main.py changes)

```
tests/test_appexport_cors.py::test_cors_header_present_on_matched_path_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_when_disabled PASSED
tests/test_appexport_cors.py::test_cors_preflight_responds_on_matched_path_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_on_unmatched_path_when_enabled PASSED

4 passed in 2.35s
```

## Full-suite run

```
cd core && uv run pytest -q
1523 passed, 148 skipped in 109.48s (0:01:49)
```

No regressions. Skip count (148) matches the pre-existing pattern of
`postgis`/`qgis`/`playwright`-marked tests requiring external services not
available in this environment — consistent with prior SP-17/SP-18a task
reports in this repo.

## Files changed

- `core/app/main.py` — 3 targeted edits (import, regex, middleware block).
- `core/tests/test_appexport_cors.py` — new file, 4 tests, verbatim from
  brief.

## Self-review findings

- Diff matches the brief's exact code for all three edits (verified via
  `git diff core/app/main.py` before commit) — no deviation.
- `git status --short` confirmed only the two intended files were staged;
  the many pre-existing modified `.superpowers/sdd/*.md` files in the
  working tree (unrelated to this task, present since before this session
  started per the initial git status) were left untouched and unstaged.
- Middleware correctly evaluated once at `create_app()` time under the
  `if is_appexport_enabled():` guard — no per-request env lookup, matching
  the `appexport_routes` router-inclusion precedent immediately below it.
- Confirmed by test that the middleware imposes zero behavior change on
  unmatched paths (`/health`) even when the flag is on, and zero behavior
  change on any path when the flag is off (middleware object never
  constructed/registered in that case).
- `ruff` is not installed in this environment/venv (`uv run ruff` fails
  with "No such file or directory") and is not a declared dependency in
  `core/pyproject.toml` — could not run a lint pass; relied on the full
  pytest suite (which includes `import-linter` contract tests, given
  `import-linter>=2.0` is a listed dependency) passing clean as the
  verification signal instead.

## Concerns

None. The change is narrowly scoped, flag-gated, matches the brief's exact
code byte-for-byte, and the full 1523-test suite passes with no
regressions.

## Fix: CORS method scoping (review finding)

### What changed and why

Task review found that `_APPEXPORT_CORS_PATH_RE` (path-only, no method
check) over-matched the plan's 7-entry allowlist. Because the middleware
applied `Access-Control-Allow-Origin: *` unconditionally to any request
whose *path* matched, it also CORS-exposed several admin/write endpoints
that share a path shape with an allowlisted one:

- `POST /collections` (create collection, admin-only) — same path as the
  allowlisted `GET /collections`.
- `GET /collections/candidates` (admin-only, lists registrable tables) —
  matched by the `(/[^/]+)?` branch treating `candidates` as a collection
  id.
- `PATCH /collections/{id}` / `DELETE /collections/{id}` — same path as
  the allowlisted `GET /collections/{id}`.
- `POST /collections/{id}/items`, `PUT .../items/{fid}`,
  `DELETE .../items/{fid}` — same paths as the allowlisted
  `GET .../items` and `GET .../items/{fid}`.

None of these are in the plan's Global Constraints allowlist (`GET
/collections`, `GET /collections/{id}`, `GET /collections/{id}/schema`,
`GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`, `POST
/collections/{id}/aggregate`, `GET /extensions`), and all require real
auth server-side — but CORS exposure alone (the response header) is
itself an information/behavior leak surface the plan explicitly said to
avoid ("Never the whole API").

Fix, per the controller/user-approved design: split into two regexes/rule
sets in `core/app/main.py`.

- `_APPEXPORT_CORS_PATH_RE` (existing, unchanged) — kept **path-only**,
  used **only** to gate the `OPTIONS` preflight branch. This is correct
  behavior, not a residual bug: a browser sends `OPTIONS` before it knows
  what the real follow-up method will be, so preflight can only be gated
  on path. The real, non-`OPTIONS` request is what must be blocked for
  disallowed methods, and preflight succeeding for a path that will later
  reject the real write request is the same shape the middleware already
  had for `POST /collections/{id}/aggregate` (a `POST`-only real endpoint
  whose preflight is also path-matched).
- `_APPEXPORT_CORS_RULES` (new) — a tuple of `(compiled_regex, method)`
  pairs, one per allowlist entry, checked only on the non-`OPTIONS`
  branch. A real request only gets `Access-Control-Allow-Origin` if its
  method+path pair matches one of the 7 rules exactly.
- The `GET /collections/{id}` rule uses a negative lookahead,
  `^/collections/(?!candidates$)[^/]+$`, to explicitly exclude the static
  admin-only `GET /collections/candidates` route
  (`app/collections/routes.py`), which otherwise has the identical path
  shape as `/collections/{real-id}`. Verified by grepping
  `app/collections/routes.py` for all `@router.` path declarations: the
  only other GET route under a single `/collections/<segment>` shape is
  this one; `POST /collections/empty` doesn't collide because it's a
  `POST`, not gated by the `GET` rule.

`appexport_cors`'s body now branches on `request.method == "OPTIONS"`
first (path-only check against `_APPEXPORT_CORS_PATH_RE`, unchanged
behavior) and otherwise checks `_APPEXPORT_CORS_RULES` (method AND path)
before adding the header to the real response.

### New/changed tests (`core/tests/test_appexport_cors.py`)

The original 4 tests are unmodified. Added 4 new tests:

1. `test_cors_header_absent_on_post_collections_when_enabled` — `POST
   /collections` gets no CORS header.
2. `test_cors_header_absent_on_collections_candidates_when_enabled` —
   `GET /collections/candidates` gets no CORS header (the concrete
   over-match this fix targets; caught a first draft of the fix that
   still used a bare `[^/]+` without the `candidates` exclusion — this
   test failed against that draft with a 401 response that still carried
   `access-control-allow-origin: *`, confirming the negative lookahead
   was necessary, not just defensive).
3. `test_cors_header_absent_on_collection_write_endpoints_when_enabled` —
   `PATCH`/`DELETE /collections/{id}`, `POST .../items`, `PUT
   .../items/{fid}`, `DELETE .../items/{fid}` all get no CORS header.
4. `test_cors_preflight_still_204_on_write_paths_when_enabled` — `OPTIONS
   /collections/{id}/items` still returns `204` with the CORS preflight
   headers, proving the preflight branch's path-only behavior is
   intentionally preserved (not weakened by this fix).

### Focused test output (`test_appexport_cors.py`)

```
tests/test_appexport_cors.py::test_cors_header_present_on_matched_path_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_when_disabled PASSED
tests/test_appexport_cors.py::test_cors_preflight_responds_on_matched_path_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_on_unmatched_path_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_on_post_collections_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_on_collections_candidates_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_header_absent_on_collection_write_endpoints_when_enabled PASSED
tests/test_appexport_cors.py::test_cors_preflight_still_204_on_write_paths_when_enabled PASSED

8 passed in 2.78s
```

### Full-suite output

```
1527 passed, 148 skipped in 109.85s (0:01:49)
```

No regressions (the pre-fix full-suite run in the original report above
recorded 1523 passed; the delta of +4 is exactly the 4 net new tests
added to this file — an intermediate draft run briefly had the
`candidates` test fail with a 401 that still carried the CORS header,
before the negative-lookahead exclusion was added; the final run is
clean).

### Files changed

- `core/app/main.py` — split `_APPEXPORT_CORS_PATH_RE` (path-only, now
  documented as OPTIONS-preflight-only) from new `_APPEXPORT_CORS_RULES`
  (method+path pairs), and updated `appexport_cors` to gate the
  non-`OPTIONS` branch on `_APPEXPORT_CORS_RULES` instead of
  `_APPEXPORT_CORS_PATH_RE`.
- `core/tests/test_appexport_cors.py` — added the 5 regression tests
  above.

### Concerns

None outstanding. The fix is scoped exactly to the review finding, both
Critical over-match cases named in the finding (`POST /collections`,
`GET /collections/candidates`) now have explicit regression tests, and
the full core suite is green with no regressions.
