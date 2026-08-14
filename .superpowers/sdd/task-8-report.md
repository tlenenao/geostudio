# Task 8 report: REST routes + wiring (main.py, instance flag)

## What was implemented

- `core/app/appexport/routes.py` (new): `POST /app-exports` and
  `GET /app-exports/jobs/{job_id}`, byte-for-byte mirroring
  `app/export/routes.py`'s structure (swapping `format` → `mode`,
  `/export` → `/app-exports`, `export_repo`/`render_export_task` →
  `appexport_repo`/`build_app_export_task`, bucket env var
  `S3_APPEXPORTS_BUCKET` defaulting to `geostudio-appexports`).
  `_SUPPORTED_MODES = {"static"}` gates `mode`, returning 422 for anything
  else (SP-18a only builds the static bundle; connected/standalone are
  future SP-18b/c).
- `core/app/main.py`: imported `appexport_routes` and `is_appexport_enabled`;
  mounted the router conditionally (`if is_appexport_enabled(): ...`),
  right after the existing `export_routes` block; added the
  `S3_APPEXPORTS_BUCKET` dependency override next to `export_routes`'s,
  inside the existing `if s3_endpoint and s3_access_key and s3_secret_key:`
  block.
- `core/app/instance/routes.py`: imported `is_appexport_enabled`, added
  `"appExportEnabled": is_appexport_enabled()` to the `/instance` response
  dict.
- `core/tests/test_appexport_routes.py` (new): 6 tests mirroring
  `test_export_routes.py`'s fixture pattern (`_FakeS3Client`,
  `_fake_deferrer`, `env` fixture with `app.dependency_overrides` for
  `db.get_session`, `ingestion_routes.get_s3_client`,
  `appexport_routes.get_task_deferrer`).

## Deviation from the brief (found during RED, not guessed from memory)

The brief's test fixture built the seed `app`-kind config as
`BuilderConfig(kind="app", dataSources=[], pages=[])`. Running it (Step 2)
surfaced a real `pydantic.ValidationError`, not the expected
`ModuleNotFoundError` — before `routes.py` even existed, the fixture itself
was broken: `BuilderConfig`'s `_require_kind_payload` validator
(`app/configs/schemas.py:390-391`) requires a top-level `layout` for
`kind in ("app", "dashboard", "site")`. `test_export_routes.py` doesn't hit
this because it seeds a `kind="map"` config instead. I checked how other
tests in this same plan build a minimal `app`-kind config
(`tests/test_create_bookmark.py`, `tests/test_mcp_tools_bookmark_create.py`,
`tests/test_configs_schemas.py`) and added the same minimal payload:
`layout={"type": "grid", "breakpoints": {}, "items": []}`. After that the
6 tests ran exactly as specified with no further changes needed.

## TDD evidence

**RED** (`cd core && uv run pytest tests/test_appexport_routes.py -v`,
before `routes.py` existed):
```
ImportError: cannot import name 'routes' from 'app.appexport'
1 error in 0.32s
```
(then, after creating `routes.py` but before the `BuilderConfig` fixture
fix — this is the real RED that matters, since the import error is trivial):
```
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for BuilderConfig
E     Value error, app config requires a layout [type=value_error, ...]
6 errors in 1.96s (procrastinate AppNotOpen noise in captured logs is a
red herring — it's a swallowed embedding-enqueue side effect, not the
actual test failure)
```

**GREEN** (`cd core && uv run pytest tests/test_appexport_routes.py -v`,
after adding `layout=...` to the fixture):
```
tests/test_appexport_routes.py::test_post_app_export_requires_flag_enabled PASSED
tests/test_appexport_routes.py::test_post_app_export_creates_job_and_returns_202 PASSED
tests/test_appexport_routes.py::test_post_app_export_denies_user_without_read_access PASSED
tests/test_appexport_routes.py::test_post_app_export_rejects_invalid_mode PASSED
tests/test_appexport_routes.py::test_get_app_export_job_reports_status PASSED
tests/test_appexport_routes.py::test_get_app_export_job_done_status_includes_result_url PASSED
6 passed in 2.76s
```

## Full suite run

`cd core && uv run pytest -q`

First run surfaced 5 pre-existing regressions — all strict `response.json()
== {...}` equality assertions against `/instance` in
`tests/test_etl_enabled_flag.py` (2), `tests/test_export_enabled_flag.py`
(1), `tests/test_read_only_mode.py` (2) — that didn't anticipate the new
`appExportEnabled` key. Fixed by adding `"appExportEnabled": False` (all
five assertions run with the flag unset/default) to each expected dict, in
the same position as `exportEnabled`/`tileset3dEnabled` etc. (`tests/test_tileset3d_enabled_flag.py`
and `tests/test_terrain3d_enabled_flag.py` don't use strict dict equality,
so they needed no change.)

Command: `cd core && uv run pytest -q`
```
1508 passed, 148 skipped in 109.18s (0:01:49)
```
No collection errors. The 148 skipped are the existing postgis-marked tests
(need docker), unrelated to this task.

Also ran `uv run lint-imports` (import-linter, per CLAUDE.md's "frontières
de modules outillées"): `Contracts: 1 kept, 0 broken.`

## Files changed

- `core/app/appexport/routes.py` (new)
- `core/app/main.py` (modified: import + conditional router mount + bucket
  dependency override)
- `core/app/instance/routes.py` (modified: import + `appExportEnabled` key)
- `core/tests/test_appexport_routes.py` (new)
- `core/tests/test_etl_enabled_flag.py` (modified: 2 assertions)
- `core/tests/test_export_enabled_flag.py` (modified: 1 assertion)
- `core/tests/test_read_only_mode.py` (modified: 2 assertions)

## Self-review (against the 4 points asked)

1. **Router only mounted when `is_appexport_enabled()` is true, 404 when
   disabled.** Confirmed: `main.py` has `if is_appexport_enabled():
   app.include_router(appexport_routes.router)`, mirroring
   `is_export_enabled()`/`export_routes`. Test
   `test_post_app_export_requires_flag_enabled` verifies 404 (not the
   FastAPI-default 405) when the flag is off, since the route simply
   doesn't exist on that app instance.
2. **Read-access via `can()`/`get_access_facts`, 404 (not 403) for both
   "doesn't exist" and "no read access".** Confirmed:
   `_require_export_read_access` (verbatim copy of
   `export.routes._require_export_read_access`) does
   `facts = items_repo.get_access_facts(...)`, then
   `if facts is None or not can(..., action="read", ...): raise
   HTTPException(404, ...)` — single branch, single status code, no
   distinction leaked to the caller. Test
   `test_post_app_export_denies_user_without_read_access` confirms 404 for
   the "item exists but stranger has no access" case; the "job id doesn't
   exist" case for GET is exercised by `_require_export_read_access` never
   even being reached (job lookup itself 404s first) — same shape as
   `export.routes.get_export_job_route`.
3. **`session.commit()` before `defer_task()`.** Confirmed in
   `create_app_export_route`: `session.commit()` is the line immediately
   before `defer_task(job.id, user.tenant_id)`, with the same inline
   rationale comment as `export_routes`/`run_pipeline_route`.
4. **Full suite passes with no collection errors.** Confirmed: `1508
   passed, 148 skipped`, 0 failed, 0 errors, 0 collection errors.
   Import-linter contract also kept.

## Concerns

- None blocking. One judgment call worth flagging: `/app-exports` was
  **not** added to `main.py`'s `_EXPORT_PATH_RE` (the regex that exempts
  export-family POST routes from the read-only demo guard). The brief
  doesn't mention this, and no test in the brief's spec covers it. By the
  same reasoning used for `/export` (SP-16a: "export is a read action for
  the source app, doesn't write business data"), `/app-exports` arguably
  deserves the same exemption — it writes only an `AppExportJob` audit-ish
  row, not business data. I left this out of scope since it wasn't in the
  brief and no test demanded it; flagging it here in case Task 14 (branch
  review) or Task 9-13 (shell wiring) need the demo mode to support
  triggering an app export.
- The `test_appexport_routes.py` fixture fix (adding `layout=...`) is a
  genuine correction to the brief's guessed code, not a guess of my own —
  it was forced by an actual pydantic `ValidationError` at RED time, then
  cross-checked against 3 other real tests in the same plan/repo that
  build minimal `app`-kind `BuilderConfig`s the same way.

## Fix: read-only-mode exemption

**What changed and why.** `POST /app-exports` (SP-18a, `core/app/appexport/routes.py`)
was not exempted from the `read_only_guard` middleware in `core/app/main.py`,
unlike its sibling `/export` (SP-17a). The guard's `_EXPORT_PATH_RE` regex
(`core/app/main.py:46`) matched `/export`, `/collections/{id}/export[/items]`,
and `/datasets/{id}/arcgis/export[/items]` but not `/app-exports` — so on a
read-only demo instance, triggering an app export got a spurious 403 before
ever reaching the appexport router, even though (same as `/export`) it only
packages/renders existing public data and writes no business data. Extended
the regex to also match `^/app-exports$`:

```python
_EXPORT_PATH_RE = re.compile(
    r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$|^/export$|^/app-exports$"
)
```

**TDD evidence.**
- RED: added `test_post_app_export_allowed_in_read_only_demo_mode` to
  `core/tests/test_appexport_routes.py` (mirrors
  `test_post_export_allowed_in_read_only_demo_mode` in
  `test_export_routes.py`, same `env` fixture/dependency-override pattern).
  Run against the unfixed regex: `POST /app-exports` returned `403
  Forbidden` (`"Mode démo : lecture seule, écritures désactivées."`)
  instead of the expected `202` — 1 failed.
- GREEN: after the regex fix, `uv run pytest tests/test_appexport_routes.py -q`
  → `7 passed`.

**Full suite run.** `cd core && uv run pytest -q` →
`1509 passed, 148 skipped` in 107.37s. No regressions; read-only-mode
tests (`test_read_only_mode.py`, `test_export_routes.py`,
`test_appexport_routes.py`) all green.

**Commit.** See below (created after this report was appended).
