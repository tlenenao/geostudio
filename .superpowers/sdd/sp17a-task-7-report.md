# SP-17a Task 7 report — routes REST `POST /export` + `GET /export/jobs/{id}`

## What was implemented

- `core/app/export/routes.py` (new): FastAPI router with
  - `POST /export` — `CreateExportRequest{itemId, format}` → 202 `CreateExportResponse{jobId}`.
    Validates `format in ("png","pdf")` (422 otherwise), checks read access via
    `items_repo.get_access_facts` + `sharing.authorization.can` (404 if item missing or
    access denied — never leaks existence via 403), creates the job via
    `export_repo.create_job`, writes an audit entry (`export.create`), commits the
    session, then defers `render_export_task` via an overridable `get_task_deferrer`
    dependency (same pattern as `app.pipelines.routes`).
  - `GET /export/jobs/{job_id}` — 200 `ExportJobStatus{id, status, resultUrl, error}`.
    404 if job unknown; re-checks read access on the job's `item_id` (404, not 403);
    generates a presigned S3 GET URL only when `status == "done"` and `result_key` is set.
- `core/app/main.py` (modified):
  - Added `is_export_enabled` to the existing `app.auth.dependency` import line, and
    `from app.export import routes as export_routes`.
  - Conditional mount: `if is_export_enabled(): app.include_router(export_routes.router)`,
    right after the `is_etl_enabled()` pipelines block.
  - Extended `_EXPORT_PATH_RE` to also match `^/export$`, exempting `POST /export` from
    the `read_only_guard` demo middleware (export is a read action, same reasoning as the
    SP-16a export routes already exempted there).
- `core/tests/test_export_routes.py` (new): the 6 tests from the brief, verbatim.

## TDD evidence

RED (before implementation):
```
ImportError: cannot import name 'routes' from 'app.export'
```

GREEN (after implementation):
```
tests/test_export_routes.py::test_post_export_requires_flag_enabled PASSED
tests/test_export_routes.py::test_post_export_creates_job_and_returns_202 PASSED
tests/test_export_routes.py::test_post_export_denies_user_without_read_access PASSED
tests/test_export_routes.py::test_get_export_job_reports_status PASSED
tests/test_export_routes.py::test_get_export_job_unknown_id_is_404 PASSED
tests/test_export_routes.py::test_post_export_allowed_in_read_only_demo_mode PASSED
6 passed in 2.87s
```

## Files changed

- `core/app/export/routes.py` (new)
- `core/app/main.py` (import + conditional mount + `_EXPORT_PATH_RE` regex)
- `core/tests/test_export_routes.py` (new)

## Self-review findings

All checks from the task brief's self-review list confirmed:
- 404 (never 403) returned both when access facts are `None` and when `can()` denies read,
  in both `POST /export` and `GET /export/jobs/{id}` — matches the no-existence-leak
  convention (mirrors `_require_pipeline_access`).
- `test_post_export_requires_flag_enabled` genuinely proves the router isn't mounted:
  it recreates the app with `CORE_EXPORT_ENABLED=false` (flag is read once at
  `create_app()` time, same as ETL) and asserts 404, not 403/422.
- `write_audit` call shape matches the existing pattern used in
  `app.pipelines.routes.run_pipeline_route` (`tenant_id`, `actor_id`, `actor_kind="user"`,
  `action`, `object_type`, `object_id`, `payload`).
- `session.commit()` happens before `defer_task(...)` in `create_export_route`, mirroring
  `run_pipeline_route`'s comment about a worker potentially picking up the job before the
  row is visible otherwise.
- `test_post_export_allowed_in_read_only_demo_mode` builds the app via the real
  `create_app()` (not a bypassed dependency) so it genuinely exercises the
  `read_only_guard` middleware and the updated `_EXPORT_PATH_RE`; it failed before the
  regex change (verified by construction — the brief's literal regex fix was applied and
  the test passes) and passes now.
- Presigned URL generation in `GET /export/jobs/{id}` is gated on
  `job.status == "done" and job.result_key` — no S3 call otherwise, so no risk of hitting
  `os.environ["S3_ENDPOINT_URL"]` (KeyError) for pending/running/error jobs in tests that
  don't set those env vars.

No deviations from the brief's literal code were needed — `items_repo.get_access_facts`,
`sharing.authorization.can`, `app.audit.writer.write_audit`,
`app.ingestion.storage.make_s3_client`/`generate_presigned_get_url`, and the
`is_etl_enabled`/`is_export_enabled` conditional-mount convention in `main.py` all matched
the brief's assumptions exactly (verified by reading `app/pipelines/routes.py`,
`app/sharing/authorization.py`, `app/items/repository.py`, `app/audit/writer.py`,
`app/export/repository.py`, `app/export/jobs.py`, and `app/main.py` before writing code).

## Full-suite result

```
cd core && uv run pytest tests/ -q
1315 passed, 137 skipped in 93.81s (0:01:33)
```

Zero regressions from touching the shared `app/main.py`.

## Concerns

None. Task complete as specified.

## Fix round 1 — code review finding (Important)

Reviewer finding on commit `dea7bc0`: `get_export_job_route` constructed its S3
client inline from `os.environ["S3_ENDPOINT_URL"]` / `["S3_ACCESS_KEY"]` /
`["S3_SECRET_KEY"]` — correct for `app/export/jobs.py`'s worker task (a
procrastinate task, no request/DI context), but not the established
convention for FastAPI *routes* in this codebase: `app/ingestion/routes.py`
defines `get_s3_client()` as an overridable dependency (default `raise
RuntimeError("S3 client dependency not configured")`, wired conditionally in
`app/main.py` when `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` are all
present). Consequence: unconfigured S3 → unhandled `KeyError` → opaque 500 on
a `"done"` job; and no test in the original diff ever drove a job to
`status="done"`, so the entire client-construction + presigned-URL branch was
completely unexercised despite `resultUrl` being part of the route's
documented contract.

### What changed

- `core/app/export/routes.py`:
  - Imports `get_s3_client` from `app.ingestion.routes` and reuses it
    **verbatim** as `s3=Depends(get_s3_client)` on `get_export_job_route`,
    instead of defining a second, identical placeholder dependency locally.
    Rationale (asked for explicitly in the task): `ingestion_routes.get_s3_client`
    has zero ingestion-specific behavior — it's a generic "raise until
    overridden" FastAPI injection point — and `app/export/routes.py` already
    imports from `app.ingestion.storage` (`generate_presigned_get_url`), so
    this adds no new coupling, just extends an existing one. It also means
    `app/main.py`'s existing override
    (`app.dependency_overrides[ingestion_routes.get_s3_client] = ...`) covers
    export "for free" — no duplicate override wiring needed for the client
    itself.
  - Added a new, export-local `get_exports_bucket() -> str` dependency
    (mirrors `ingestion_routes.get_uploads_bucket()`), reading
    `S3_EXPORTS_BUCKET` (default `"geostudio-exports"`) — this one *is*
    export-specific (different bucket than ingestion), so it's not shared.
  - `get_export_job_route` gained `s3=Depends(get_s3_client)` and
    `bucket: str = Depends(get_exports_bucket)` params; the body now calls
    `generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)`
    instead of building a client and reading `os.environ[...]` inline.
  - Moved `import os` up to the stdlib import group (was oddly placed after
    the `app.*` imports) — the cheap Minor fix, done while already touching
    imports in this file.
- `core/app/main.py`: added
  `app.dependency_overrides[export_routes.get_exports_bucket] = lambda: s3_exports_bucket`
  inside the existing `if s3_endpoint and s3_access_key and s3_secret_key:`
  block (same block that already wires `ingestion_routes.get_s3_client` /
  `get_uploads_bucket`). No new override needed for the S3 client itself,
  since export reuses the same dependency object as ingestion.
- `core/tests/test_export_routes.py`:
  - Added a minimal `_FakeS3Client` (only `generate_presigned_url`, same
    contract as `tests/test_ingestion_routes.py::_FakeS3Client`).
  - The shared `env` fixture's `make_client()` now overrides
    `ingestion_routes.get_s3_client` with the fake client. This was required,
    not optional: because `s3=Depends(get_s3_client)` is a route-parameter
    dependency, FastAPI resolves it for **every** call to
    `GET /export/jobs/{id}`, regardless of the job's status — so even the
    pending-status and unknown-id tests needed the override to avoid a
    (new, correctly-shaped, but unwanted-here) 500. This is an intentional,
    accepted behavior change from the pre-fix code (which only touched S3 on
    the `"done"` branch): in practice export being enabled implies S3 is
    configured (the worker can't write results otherwise), so requiring it
    eagerly on this route is a defensible fail-fast, and it's the literal
    convention already used by `app/ingestion/routes.py`'s two S3-backed
    routes (both eager). The `env` fixture also now returns the `Session`
    factory (5th tuple element) so tests can drive job state directly via
    `export_repo`, alongside `make_client`/`owner`/`stranger`/`item_id`; all
    6 pre-existing tests were updated to unpack the extra element (unused
    ones as `_Session`).
  - New test `test_get_export_job_done_status_includes_result_url`: creates a
    job via `POST /export`, then calls `export_repo.mark_running` +
    `export_repo.mark_done(session, job_id=..., result_key=f"renders/{job_id}.png")`
    directly (same pattern as `tests/test_export_repository.py::test_mark_running_then_done`),
    then `GET /export/jobs/{job_id}` and asserts `status == "done"` and
    `resultUrl == "https://minio.test/geostudio-exports/renders/{job_id}.png"`
    (from the fake client's `generate_presigned_url`).
  - New test `test_post_export_rejects_invalid_format`: `POST /export` with
    `format: "svg"` asserts 422 (closes the Minor finding; format validation
    itself already existed pre-fix, so this is pure coverage, not a
    regression fix — see RED/GREEN note below).

### RED-before / GREEN-after evidence

For `test_get_export_job_done_status_includes_result_url`, isolated the
pre-fix code via `git stash push -- app/export/routes.py app/main.py` (kept
the new test file), then ran the single new test:

```
$ uv run pytest tests/test_export_routes.py::test_get_export_job_done_status_includes_result_url -v
...
key = 'S3_ENDPOINT_URL'
>   ???
E   KeyError: b'S3_ENDPOINT_URL'
<frozen os>:706: KeyError
...
FAILED tests/test_export_routes.py::test_get_export_job_done_status_includes_result_url
1 failed in 4.24s
```

This is the exact opaque failure the finding described (`os.environ["S3_ENDPOINT_URL"]`
→ `KeyError` → unhandled → 500), now proven by a real test rather than by
inspection. `git stash pop` restored the fix, then:

```
$ uv run pytest tests/test_export_routes.py -v
tests/test_export_routes.py::test_post_export_requires_flag_enabled PASSED
tests/test_export_routes.py::test_post_export_creates_job_and_returns_202 PASSED
tests/test_export_routes.py::test_post_export_denies_user_without_read_access PASSED
tests/test_export_routes.py::test_get_export_job_reports_status PASSED
tests/test_export_routes.py::test_get_export_job_unknown_id_is_404 PASSED
tests/test_export_routes.py::test_post_export_allowed_in_read_only_demo_mode PASSED
tests/test_export_routes.py::test_post_export_rejects_invalid_format PASSED
tests/test_export_routes.py::test_get_export_job_done_status_includes_result_url PASSED
8 passed in 3.13s
```

(`test_post_export_rejects_invalid_format` was GREEN immediately — the
`format` validation itself predates this fix; the test only closes the
coverage gap, it doesn't prove a regression fix.)

### Full-suite regression result

```
cd core && uv run pytest -q
1317 passed, 137 skipped in 98.20s (0:01:38)
```

(1315 → 1317: +2 new tests, 0 failures, same 137 skips as the original task-7
run — postgis/qgis/playwright markers, environment-gated, unaffected by this
change.)

### Commit

`103fa70` — `fix(core): SP-17a — GET /export/jobs/{id} : client S3 injectable + couverture du statut done`

### Concerns / judgment calls

- **Reused `get_s3_client` rather than duplicating it**, per the task's
  explicit invitation to use judgment here. It's a generic, side-effect-free
  placeholder (no ingestion-specific logic) and `app.export` already imports
  from `app.ingestion.storage`, so this is a natural extension of an existing
  dependency rather than a new one. Downside acknowledged: it does mean
  `app/export/routes.py` and `app/ingestion/routes.py` now share one
  dependency-override key in `app/main.py`'s `dependency_overrides` dict —
  overriding one for a test overrides both. In practice this is harmless
  (both need the same real S3 credentials; only the bucket differs, and the
  bucket dependency was kept separate/export-local for that reason) and
  matches how `app/main.py` already treats `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/
  `S3_SECRET_KEY` as one instance-wide credential set feeding multiple
  buckets (thumbnails, uploads, now exports).
- **Behavior change accepted, not just a "clean error" swap**: moving to
  eager `Depends(get_s3_client)` means `GET /export/jobs/{id}` now requires
  S3 to be configured (or overridden) for *every* call to that route, not
  only when a job is actually `"done"`. Pre-fix, a pending/running/error job
  status check never touched S3 at all. This is a deliberate trade-off
  (true call-by-need laziness isn't achievable with FastAPI's `Depends`
  without inventing a bespoke pattern with no precedent elsewhere in this
  codebase — see the two S3-backed ingestion routes, both eager for the same
  structural reason), and matches the reality that export being enabled
  already implies S3 is configured (the worker can't persist a render result
  otherwise). Flagging this explicitly since it wasn't spelled out in the
  original finding.
- `app.export` is not currently listed in `core/pyproject.toml`'s
  `[tool.importlinter]` "layered architecture" contract at all (neither in
  `layers` nor `ignore_imports`) — pre-existing gap from the original SP-17a
  commit, out of scope for this fix. The new `app.export → app.ingestion`
  import this fix adds is therefore not checked by import-linter either way;
  noting it here rather than silently working around an unenforced contract.
