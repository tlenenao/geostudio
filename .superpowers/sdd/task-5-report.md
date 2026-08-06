# Task 5 report — Routes + admin gate + audit + `app.main` wiring

## What was implemented

- `core/tests/conftest.py` — added a fixed, committed, dev/test-only
  `CORE_SECRETS_MASTER_KEY` default via `os.environ.setdefault(...)`,
  right after the imports, with the docstring update from the brief.
  `setdefault` (not `setenv`) so tests that explicitly monkeypatch the var
  (e.g. `test_secrets_crypto.py`) remain in control of their own value.
- `core/app/secrets/routes.py` (new) — `POST /secrets`, `GET /secrets`,
  `DELETE /secrets/{id}`, all admin-gated via a locally-defined
  `_require_admin(user)` helper (not extracted to a shared module, per
  the codebase's existing per-module duplication convention). Create
  checks name uniqueness (409 on conflict) before encrypting via
  `crypto.encrypt`. Delete looks up the secret tenant-scoped first (404
  if absent, which also naturally covers cross-tenant reads since the
  repository query filters on `tenant_id`) then deletes. Both mutating
  routes call `write_audit(...)` with `action="secret.create"` /
  `"secret.delete"` and a payload containing only `name`/`kind` — never
  the secret value, ciphertext, or nonce. The response model
  `ConnectorSecretOut` only exposes `id`/`name`/`kind`/`createdAt`/
  `updatedAt`.
- `core/app/main.py`:
  - import block: `from app.secrets import crypto as secrets_crypto` and
    `from app.secrets import routes as secrets_routes`, inserted between
    the `public_routes` and `schemas_router` imports (alphabetical
    position matched what was actually on disk).
  - `create_app()`: `secrets_crypto.load_master_key()` added as the very
    first statement after `observability.setup()`, before any DB/engine
    work — fails fast (`KeyError`/`RuntimeError`) if
    `CORE_SECRETS_MASTER_KEY` is absent or malformed.
  - router mount: `app.include_router(secrets_routes.router)` added
    immediately after `app.include_router(extensions_routes.router)`.
- `core/tests/test_secrets_routes.py` (new) — the 12 tests from the
  brief, transcribed verbatim.

## TDD evidence

**RED** — `cd core && uv run pytest tests/test_secrets_routes.py -v`
before `routes.py`/`main.py` changes: 9 failed, 3 passed. Failures were
exactly as predicted by the brief: every HTTP-hitting test got a 404 (no
`/secrets` route mounted yet — three of those manifested as
`JSONDecodeError` on `.json()` of a plain-text 404 body rather than an
assertion failure, but all traced to the same missing-route cause), and
`test_create_app_fails_fast_without_master_key` failed with
`Failed: DID NOT RAISE KeyError` (no eager check in `create_app()` yet).
The 3 tests that passed were tests not dependent on route wiring or the
eager check reaching an assertion in this particular way — consistent
with the brief's expectation.

**GREEN** — `cd core && uv run pytest tests/test_secrets_routes.py -v`
after implementing `routes.py` and wiring `main.py`:

```
tests/test_secrets_routes.py::test_create_requires_admin PASSED
tests/test_secrets_routes.py::test_list_requires_admin PASSED
tests/test_secrets_routes.py::test_delete_requires_admin PASSED
tests/test_secrets_routes.py::test_create_and_list PASSED
tests/test_secrets_routes.py::test_create_response_never_leaks_secret_value PASSED
tests/test_secrets_routes.py::test_list_response_never_leaks_secret_value PASSED
tests/test_secrets_routes.py::test_create_duplicate_name_conflicts PASSED
tests/test_secrets_routes.py::test_delete_removes_secret PASSED
tests/test_secrets_routes.py::test_delete_missing_returns_404 PASSED
tests/test_secrets_routes.py::test_delete_cross_tenant_returns_404 PASSED
tests/test_secrets_routes.py::test_mutations_are_audited PASSED
tests/test_secrets_routes.py::test_create_app_fails_fast_without_master_key PASSED

12 passed in 2.34s
```

## Layering contract

`cd core && uv run lint-imports`:

```
Analyzed 144 files, 414 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

## Full suite run

`cd core && uv run pytest -q`:

```
1075 passed, 127 skipped in 68.98s (0:01:08)
```

`--collect-only` confirms 1202 total tests collected (1075 + 127 = 1202,
internally consistent, no errors). Skip count (127) exactly matches the
task's stated baseline skip count, confirming no accidental skip-status
changes anywhere in the repo. Zero failures, zero errors.

Note on the pass count: the task instructions estimated "roughly 1063
passed" (baseline 1051 + this task's 12 new tests) as the expected
number. The actual full-suite run shows 1075 passed — 12 more than that
estimate. I could not find a "1051 passed" figure recorded in
`task-4-report.md` (it only reports the scoped 12/12 for
`test_secrets_repository.py`), so the 1051 baseline in the task
instructions appears to be an approximation from elsewhere rather than a
number I can directly diff against. What I *can* confirm directly: (a)
`git status` shows only the four files this task was supposed to touch
changed under `core/`, so no other test file was added or modified by
this task; (b) the skip count (127) is unchanged; (c) there are zero
failures and zero errors. I'm treating this as expected drift (the
instructions explicitly allow for "some drift is fine") rather than a
regression, since there's no mechanism by which this task's changes
could have caused 12 previously-failing-or-absent tests to start
passing — the only behavior change introduced is the eager
`load_master_key()` call and the new `/secrets` routes, both scoped to
this feature.

## Files changed

- `core/tests/conftest.py` (modified)
- `core/app/secrets/routes.py` (new)
- `core/app/main.py` (modified)
- `core/tests/test_secrets_routes.py` (new)

## Self-review findings

- **Completeness**: all 9 brief steps executed in order, including the
  full-suite run (step 8).
- **Quality**: `routes.py`, the `main.py` edits, and the `conftest.py`
  edit were transcribed verbatim from the brief — diffed by eye against
  the brief's code blocks before and after writing. No extra routes, no
  extra scope. `_require_admin` is a local, non-exported helper — not
  extracted to a shared module (matches the codebase's existing
  per-module duplication convention, per the brief and the task
  instructions).
- **Discipline**: confirmed via `grep` that `routes.py` defines exactly
  three routes — `POST /secrets`, `GET /secrets`, `DELETE
  /secrets/{secret_id}` — no `GET /secrets/{id}`, no `PUT`/`PATCH`
  route. Rotation is delete+recreate only, per the plan's non-goals.
- **Testing**: 12/12 new tests pass, pristine output (no warnings beyond
  a pre-existing benign "Attempting to instrument while already
  instrumented" OTel warning present across the whole suite, unrelated
  to this change). Full suite: 1075 passed, 127 skipped, 0 failed, 0
  errors. `lint-imports`: `Contracts: 1 kept, 0 broken.`
- Verified only the 4 intended files were staged before commit (`git
  status` before `git add`) — the unrelated `.superpowers/sdd/*` working
  tree modifications flagged in the task instructions as "not your
  concern" were left untouched and unstaged.

## Issues or concerns

None. This is the terminal task of the SP-15e plan; no further wiring
is expected from this task (SP-15f, out of scope, will be the next
consumer — of `repository.get_secret_payload` only).

## Final Review Fix

Applied both findings from the final whole-branch review of SP-15e
(commits 2b3f202..f8fbab5 on `dev`). Commit `d958d9b`.

### Finding 1 (Important) — `CORE_SECRETS_MASTER_KEY` unwired

`core/app/main.py`'s `create_app()` calls
`secrets_crypto.load_master_key()` eagerly (right after
`observability.setup()`, before any DB work), which reads
`os.environ["CORE_SECRETS_MASTER_KEY"]` and raises `KeyError` if unset —
this would crash-loop the `core` container on the documented `docker
compose up -d` path, since the var was neither documented in
`.env.example` nor wired into `docker-compose.yml`.

Fixes:
- `.env.example` — added a new `─── Cœur : coffre de secrets
  connecteurs (SP-15e) ───` section (right after the
  `CORE_READ_ONLY_MODE`/`CORE_ETL_ENABLED` block), documenting that the
  value must be a base64-encoded 32-byte AES-256 key, with the
  generation hint `openssl rand -base64 32`, and an explicit warning
  not to commit a real key. Left the value blank (no dummy key
  committed).
- `docker-compose.yml` — added `CORE_SECRETS_MASTER_KEY:
  ${CORE_SECRETS_MASTER_KEY}` to the `core` service's `environment:`
  block (no `:-default` fallback, matching the `MINIO_USER`/
  `MINIO_PASSWORD` passthrough style for required-no-default vars —
  the crypto module is meant to fail fast, not silently default).
- `docker-compose.prod.yml` — **not touched**, per instructions.
  Verified by inspection that the prod overlay's `core.environment`
  block only overrides `CORE_AUTH_MODE`/`CORE_OIDC_ISSUER`/
  `CORE_OIDC_JWKS_URL`/`CORE_BASE_URL` and does NOT re-declare
  `CORE_READ_ONLY_MODE` or `CORE_MCP_AUDIENCE` — yet those vars are
  still in effect in prod, confirming docker compose merges
  `environment:` maps between base and override files. Confirmed this
  concretely for the new var too: ran `docker compose -f
  docker-compose.yml -f docker-compose.prod.yml --env-file
  <copy-of-.env.example> config`, parsed the merged YAML, and verified
  `CORE_SECRETS_MASTER_KEY` is present in the merged `core` service's
  `environment` map. No prod-file change needed.
- **Validation**: `docker compose --env-file <copy-of-.env.example>
  config --quiet` (base file alone) exits 0, no YAML/interpolation
  errors. Same for the base+prod overlay combination. Docker was
  available in this environment (`docker compose version` → v5.1.3),
  so this was a real validation run, not a by-eye check.

### Finding 2 (Minor) — duplicate-secret race → 500 instead of 409

`core/app/secrets/routes.py`'s `create_secret_route` did a
check-then-insert (`repo.get_secret_by_name` pre-check, then
`repo.create_secret`) with a race window: two concurrent requests for
the same name can both pass the pre-check before either commits: the
second `repo.create_secret` then raises an unhandled
`sqlalchemy.exc.IntegrityError` from the
`uq_connector_secrets_tenant_name` constraint, surfacing as a bare 500.

Fix: wrapped the `repo.create_secret(...)` call in a
`try`/`except IntegrityError: raise HTTPException(409, detail="secret
name already exists")` — same detail string as the existing pre-check's
409, for a consistent client-facing error. Kept the pre-check in place
(still a useful fast-path avoiding a wasted round-trip in the common
case).

Matched the existing precedent in `core/app/features/routes.py`
(`create_feature`, `except IntegrityError: raise HTTPException(409,
...)`) — that route also does **not** call `session.rollback()`
explicitly inside the `except` block. Verified why that's correct and
sufficient here too: `app/db.py`'s `request_scoped_session` (the
generator wrapping the whole request's session) already does
`except Exception: session.rollback(); raise` around the entire
request. Since the route re-raises `HTTPException` out of its own
`except IntegrityError` block, that exception propagates up through
`request_scoped_session`, which performs the rollback. No manual
`session.rollback()` needed in the route itself — adding one would
just be redundant with the existing wrapper, which is presumably why
the `features/routes.py` precedent doesn't do it either.

### Tests

- `core/tests/test_secrets_routes.py::test_create_duplicate_name_conflicts`
  (existing) — still passes, still exercises the pre-check's 409 path
  (unchanged, single sequential request).
- Added `test_create_concurrent_duplicate_race_returns_409` — simulates
  the actual race by monkeypatching `secrets_routes.repo.get_secret_by_name`
  to always return `None` (i.e. as it would report for both racing
  requests, since neither has committed yet when the other's pre-check
  runs), then issues two sequential `POST /secrets` calls with the same
  name through the real route/session stack. The pre-check is bypassed
  by the patch, so the second call falls through to the real
  `repo.create_secret`, which hits the actual
  `uq_connector_secrets_tenant_name` DB constraint (SQLite, in-memory,
  same schema as Alembic). Asserts the second response is 409 with the
  same `detail` as the pre-check path — this exercises the new `except
  IntegrityError` branch for real, not just in theory.
- `uv run pytest tests/test_secrets_routes.py -v` → **13/13 passed**
  (12 pre-existing + 1 new).
- `uv run pytest -q` (full suite) → **1076 passed, 127 skipped, 0
  failed** (was 1075 passed before the new test was added; no
  regressions elsewhere).
- `uv run lint-imports` → `Contracts: 1 kept, 0 broken.` (unaffected,
  as expected — no new cross-module imports).

### Files touched

- `.env.example`
- `docker-compose.yml`
- `core/app/secrets/routes.py`
- `core/tests/test_secrets_routes.py`

### Concerns

None. Both findings are fixed and verified end-to-end (compose config
validation with docker actually available, and a real race-path test
rather than a theoretical one). `docker-compose.prod.yml` intentionally
left untouched, with the merge behavior verified concretely rather than
assumed.
