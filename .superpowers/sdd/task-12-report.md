# Task 12 report — real E2E: cold-started standalone container serves the app from a real snapshot

## What I did

1. **Step 1** — Registered the `docker` pytest marker in `core/pyproject.toml`, appending it to the existing `markers` list exactly as specified in the brief:
   ```toml
   "docker: nécessite un démon Docker réel (build local de l'image, jamais un pull) ; skippé sinon",
   ```

2. **Step 2** — Created `core/tests/test_appexport_standalone_e2e.py` with the brief's code **verbatim**. Before writing it I cross-checked every referenced symbol against the real code to catch drift early:
   - `write_snapshot(session, *, tenant_id, config, snapshot_dir, max_records_per_source=50_000)` in `core/app/appexport/snapshot.py` — signature matches.
   - `build_standalone_bundle_zip(config, *, snapshot_dir)` in `core/app/appexport/bundler.py` — matches, and confirmed it writes `data/geostudio-app-config.json`, `docker-compose.yml`, `README.md`, plus the snapshot tree under `data/`.
   - `create_collection`, `insert_feature`, `apply_collection_ddl`, `get_or_create_default_tenant`, `get_or_create_user`, `rls_scope`, `introspect_table`, `BuilderConfig`/`DataSource`/`Layout`/`LayoutItem`/`Page` — all signatures matched the brief's usage exactly.
   - `deploy/appexport-standalone/Dockerfile` exists, builds the shell export runtime + the mini-server image, `CMD ["uvicorn", "app.appexport.miniserver.main:app", ...]`.
   - `core/app/appexport/miniserver/main.py` — confirmed routes `GET /geostudio-app-config.json`, `GET /collections/{id}/items`, `POST /collections/{id}/aggregate`, and the catch-all `StaticFiles(html=True)` mount at `/` serving `index.html` for `GET /` — all match what the test asserts.
   - `pg_engine` fixture in `core/tests/conftest.py` — confirmed it skips with a `postgis` reason string when `CORE_TEST_DATABASE_URL` is unset.

   No deviation from the brief's code was needed.

## Step 3 — Real pass (Docker + Postgres both available)

Command:
```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5432/gis_test" uv run pytest tests/test_appexport_standalone_e2e.py -v -s
```

Full output:
```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/lenen/projets/geostudio/core
configfile: pyproject.toml
plugins: anyio-4.14.1, pytest_httpserver-1.1.5
collecting ... {"timestamp": "2026-08-15T20:08:49", "level": "INFO", "logger": "procrastinate.blueprints", "message": "Adding tasks from blueprint", ...}
{"timestamp": "2026-08-15T20:08:49", "level": "INFO", "logger": "procrastinate.periodic", "message": "Registering task app.harvest.jobs.run_harvest_sweep_task with periodic id '' to run periodically with cron */15 * * * *", ...}
{"timestamp": "2026-08-15T20:08:49", "level": "INFO", "logger": "procrastinate.periodic", "message": "Registering task app.pipelines.jobs.run_pipeline_sweep_task with periodic id '' to run periodically with cron */5 * * * *", ...}
collected 1 item

tests/test_appexport_standalone_e2e.py::test_cold_started_container_serves_app_and_snapshot {"timestamp": "2026-08-15T20:08:55", "level": "ERROR", "logger": "app.collections.repository", "message": "échec de l'enqueue du job d'embedding pour la collection t_standalone_e2e (l'écriture n'est pas affectée ; l'embedding restera NULL jusqu'au prochain write)", ..., "exception": "...procrastinate.exceptions.AppNotOpen: App was not open..."}
PASSED

============================== 1 passed in 10.01s ==============================
```

The `AppNotOpen` embedding-enqueue error is expected/benign — `create_collection` fires a best-effort procrastinate `.defer()` for semantic-search embedding that requires an opened procrastinate app, absent in this test process; the repository's own log message says explicitly "l'écriture n'est pas affectée". Same pattern as `test_appexport_freeze.py` per the test file's own docstring comment.

**Real-infrastructure evidence, not mocked:**
- `docker images` after the run shows `geostudio-appexport-standalone:e2e-test` (796f21e4fbdf / 482MB) — built by the test's `standalone_image` fixture via a real `docker build -f deploy/appexport-standalone/Dockerfile -t geostudio-appexport-standalone:e2e-test .` (never a `docker pull`; no tag has ever been published for this image on this repo). The build was fast (whole test ran in 10s) because Docker's build cache was warm — this same Dockerfile/context had already been built once under this exact tag in Task 10 (`geostudio-appexport-standalone:e2e-test`, confirmed present before this task started) and again as `:local`. A cache hit on `docker build` is still a real local build invocation, not a pull — it just means every layer's content hash matched, which is expected since neither the Dockerfile nor `shell/`/`core/app` changed between Task 10 and Task 12.
- The test itself: creates a real Postgres table + collection + RLS-scoped feature row, calls the real `write_snapshot`/`build_standalone_bundle_zip`, unzips the bundle's `data/` tree to a temp dir, `docker run -d -p <free-host-port>:8000 -v <data_dir>:/data:ro <image>` (fresh container, cold, no prior state, freshly bind-mounted data), polls `GET /geostudio-app-config.json` over real HTTP until 200, then asserts:
  - config JSON `kind == "app"`
  - `GET /collections/{id}/items` returns exactly `["Alpha"]` (the one row inserted through RLS)
  - `POST /collections/{id}/aggregate {"agg": "count"}` returns `rows[0]["value"] == 1`
  - `GET /` returns `text/html` (the prebuilt shell runtime, served via `StaticFiles(html=True)`)
  - the generated `docker-compose.yml` contains none of `postgis`/`keycloak`/`minio` (case-insensitive)
  - teardown: `docker rm -f <container_id>` in a `finally`, verified afterward with `docker ps -a` — no leftover container.

This is a genuine cold-start, unmocked proof matching SP-18c design §5.

## Step 4 — Both SKIP directions verified for real

### a) No `CORE_TEST_DATABASE_URL` set

Command:
```bash
cd core && unset CORE_TEST_DATABASE_URL && uv run pytest tests/test_appexport_standalone_e2e.py -v -rs
```

Output:
```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
...
tests/test_appexport_standalone_e2e.py::test_cold_started_container_serves_app_and_snapshot SKIPPED [100%]

=========================== short test summary info ============================
SKIPPED [1] tests/test_appexport_standalone_e2e.py:83: CORE_TEST_DATABASE_URL non défini — test postgis skippé
============================== 1 skipped in 1.78s ==============================
```
Clear SKIP, reason mentions `postgis`.

### b) `docker` genuinely unresolvable via `shutil.which`

`sudo mv /usr/bin/docker` was not usable in this environment (`sudo: A terminal is required to authenticate`, non-interactive shell). Instead I used a surgical `PATH` edit for a single command chain: stripped `/usr/bin`, `/bin` (a symlink to `/usr/bin` on this system — confirmed via `readlink -f /bin` → `/usr/bin`), and `/Docker/host/bin` (a Windows-side Docker Desktop CLI dir also on `PATH` in this WSL environment, also containing a `docker` binary) from `PATH`, while keeping `uv`'s directory (`/home/lenen/.local/bin`) intact. Verified first that this genuinely defeats `shutil.which`:
```bash
$ PATH="$NEWPATH" uv run python -c "import shutil; print('docker:', shutil.which('docker'))"
docker: None
```
Then ran the test with that same `PATH` and `CORE_TEST_DATABASE_URL` still set:
```bash
cd core && PATH="$NEWPATH" CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5432/gis_test" uv run pytest tests/test_appexport_standalone_e2e.py -v -rs
```

Output:
```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
...
tests/test_appexport_standalone_e2e.py::test_cold_started_container_serves_app_and_snapshot SKIPPED [100%]

=========================== short test summary info ============================
SKIPPED [1] tests/test_appexport_standalone_e2e.py:83: docker non disponible — test standalone E2E skippé
============================== 1 skipped in 1.75s ==============================
```
Clear SKIP, reason mentions `docker`. This is the module-scoped `standalone_image` fixture's own `pytest.skip(...)`, triggered by `_docker_available()` returning `False` because `shutil.which("docker")` returned `None` — genuinely exercised, not a documented assumption.

Nothing was renamed/moved on disk (no `mv` needed since the `sudo` path failed before touching anything) — only the `PATH` env var was altered for that single command's subshell. Confirmed `docker` was never actually disturbed:
```bash
$ which docker && docker info >/dev/null 2>&1 && echo "docker OK"
/usr/bin/docker
docker OK
```

## Step 4 (full suite) and lint-imports

Command:
```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5432/gis_test" uv run pytest -q
```

**First attempt** (immediately after the E2E pass above): `1711 passed, 5 skipped in 145.26s` — clean.

**Second and third attempts** (run back-to-back right after, while investigating the skip-direction checks): both showed `1 failed, 1710 passed, 5 skipped`. The single failure was `tests/test_report_repository.py::test_list_due_reports_respects_cron_cadence_against_last_run`, with:
```
AssertionError: assert [('cefd6f99be...', 'default')] == []
```

I investigated this rather than dismiss it, per the task's instructions. Findings:
- This test uses an **in-memory SQLite** session (`_make_session()` → `sqlite+pysqlite:///:memory:`), completely unrelated to the real Postgres DB my new test touches, and it has zero references to `appexport`/`t_standalone_e2e`/anything from this task's diff.
- Its logic: create a report with cron `*/5 * * * *`, force its one run's `created_at` to "1 minute ago" via `datetime.now(timezone.utc) - timedelta(minutes=1)`, then assert `list_due_reports(s) == []` (not due yet). `list_due_reports` computes `next_tick = croniter(policy.cron, created_at).get_next(datetime)` and compares `next_tick <= now` using a **fresh** `datetime.now(timezone.utc)` call.
- Because `croniter`'s "next tick" for `*/5 * * * *` is always the **next wall-clock minute that's a multiple of 5**, not "5 minutes after created_at", this test is inherently flaky during the **first minute of any 5-minute wall-clock block** (`:00`–`:00:59`, `:05`–`:05:59`, `:10`–`:10:59`, etc.): if "now" falls in that window, `created_at` (now − 1 min) falls in the *previous* block, and the computed `next_tick` equals the *current* block's start time, which is `<= now` — so the test spuriously asserts a false positive for "due".
- I confirmed this empirically: the failure's captured log timestamp was `2026-08-15T20:20:33` — squarely inside the `:20:00`–`:20:59` flake window. My first (passing) run's test executed around `20:08:55`, outside any such window.
- Confirmed the test is **not order-dependent or polluted by other tests**: ran it alone (`pytest tests/test_report_repository.py -v`) and all 8 tests passed, including this one, in 0.65s.
- Re-ran the full suite a fourth time, later (past the flake window): clean again —
  ```
  1711 passed, 5 skipped in 142.15s (0:02:22)
  ```

**Conclusion: this is a pre-existing, time-of-day-dependent flaky test unrelated to Task 12's diff** (no shared fixtures, no shared tables, no shared code path — `test_report_repository.py` predates and is untouched by SP-18c). It is not something this task introduced, and fixing it is out of this task's scope (not part of the brief, not related to `app.appexport`). Flagging it here rather than silently re-running until green.

Final clean full-suite run used for the "nothing broke" confirmation:
```
1711 passed, 5 skipped in 142.15s (0:02:22)
```
The 5 skips are all `qgis` (no `CORE_TEST_QGIS_WORKER_URL` sidecar available), pre-existing and expected, unrelated to this task.

### lint-imports

Command:
```bash
cd core && uv run lint-imports
```
Output:
```
Analyzed 201 files, 641 dependencies.
-------------------------------------

layered architecture KEPT

Contracts: 1 kept, 0 broken.
```
Confirms the brief's prediction: this task adds no new cross-layer import (the new test only imports `app.appexport.*`, `app.collections.*`, `app.configs.*`, `app.db`, `app.features.*`, `app.tenants.*`, `app.users.*`, `app.main` — all already-established import edges).

## Self-review

- `git diff --cached --stat` before commit showed exactly the two intended files:
  ```
  core/pyproject.toml                         |   1 +
  core/tests/test_appexport_standalone_e2e.py | 167 ++++++++++++++++++++++++++++
  2 files changed, 168 insertions(+)
  ```
- Staged explicitly by name (`git add core/pyproject.toml core/tests/test_appexport_standalone_e2e.py`), not `-A`/`-a`. The pre-existing uncommitted `.superpowers/sdd/*.md` scratch files (controller bookkeeping, present before this task started) were left untouched and unstaged.
- No leftover Docker containers after the test run (`docker ps -a` empty for this image), no leftover `t_standalone_e2e` table or polluted rows in `gis_test` (the `pg_session` fixture drops the table and truncates `collection_shares, collections, audit_log, items, users, tenants` in its teardown — verified this ran by the clean state of subsequent full-suite runs).
- No deviation from the brief's verbatim test code was required; both pyproject.toml edit and the new test file match Steps 1–2 exactly.

## Deviations from the brief

- Step 4b's PATH-manipulation mechanics: the brief suggested "temporarily rename off PATH" or, if needed, renaming the actual `docker` binary with an immediate restore. `sudo mv /usr/bin/docker` failed in this sandboxed/non-interactive environment (`sudo: A terminal is required to authenticate`), so no rename was ever attempted on disk — I used the PATH-strip approach instead (which the brief explicitly allows: "adjust so `docker` genuinely can't be found by `shutil.which`... you may need a more surgical PATH edit"). This required excluding three directories (`/usr/bin`, `/bin` — a symlink to `/usr/bin` — and `/Docker/host/bin`, a WSL/Docker-Desktop CLI dir also on `PATH`), verified with a direct `shutil.which` probe before running the actual test, to be certain the skip was genuine rather than accidental.
- The full-suite run surfaced a pre-existing, unrelated, time-of-day-dependent flaky test (`test_report_repository.py::test_list_due_reports_respects_cron_cadence_against_last_run`); investigated per the "don't give up after one attempt, investigate the real root cause" instruction, confirmed unrelated to this task's diff, and got a clean run to close out the "nothing broke" check. No code change made to that test — out of scope for Task 12.

## Commit

```
1dda9c0 test(e2e): standalone export container serves app from a real snapshot (SP-18c)
 2 files changed, 168 insertions(+)
 create mode 100644 core/tests/test_appexport_standalone_e2e.py
```
