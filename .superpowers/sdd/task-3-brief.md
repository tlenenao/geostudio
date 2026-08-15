### Task 3: `build_app_export_task` branches on `mode`

**Files:**
- Modify: `core/app/appexport/jobs.py`
- Modify: `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes: `check_export_guard(..., mode=...)` (Task 1), `build_bundle_zip(..., connection=...)` (Task 2).
- Produces: unchanged public signature `build_app_export_task(job_id: str, tenant_id: str) -> None`. For `mode="connected"`: skips `freeze_config`, reads `CORE_BASE_URL` (default `http://localhost:8200`, same default used elsewhere in this codebase for the same variable) and passes it as `connection={"coreUrl": ...}` to the bundler.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_appexport_jobs.py` (existing three tests and
`_setup`/`_fake_s3` stay as-is; add a `mode` parameter to `_setup` with
default `"static"` so existing calls — which pass none — keep testing
static mode unchanged):

Modify `_setup`'s signature and the `create_job` call inside it:

```python
def _setup(monkeypatch, tmp_path, *, with_private_source=False, mode="static"):
```

```python
        job = appexport_repo.create_job(s, tenant_id=tenant.id, item_id=item.id, user_id=owner.id, mode=mode)
```

(only those two lines change in `_setup`; everything else in the function body is untouched)

Then append these new tests at the end of the file:

```python


def test_connected_job_skips_freezing_and_embeds_core_base_url(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, mode="connected")
    monkeypatch.setenv("CORE_BASE_URL", "https://core.example.org")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)

    captured: dict = {}
    real_build_bundle_zip = __import__("app.appexport.jobs", fromlist=["build_bundle_zip"]).build_bundle_zip

    def spy_build_bundle_zip(config, **kwargs):
        captured["connection"] = kwargs.get("connection")
        captured["config"] = config
        return real_build_bundle_zip(config, **kwargs)

    monkeypatch.setattr("app.appexport.jobs.build_bundle_zip", spy_build_bundle_zip)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)

    build_app_export_task(job_id=job_id, tenant_id=tenant_id)

    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "done"
    assert captured["connection"] == {"coreUrl": "https://core.example.org"}


def test_connected_job_with_private_source_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, with_private_source=True, mode="connected")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "publique" in job.error
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: `test_connected_job_skips_freezing_and_embeds_core_base_url` FAILS
(`check_export_guard() missing 1 required keyword-only argument: 'mode'` —
`jobs.py` doesn't pass `mode` yet). `test_connected_job_with_private_source_marks_error`
fails the same way. The three pre-existing tests (now implicitly
`mode="static"` via `_setup`'s default) also fail for the same reason since
`jobs.py`'s call to `check_export_guard` has no `mode=` kwarg at all yet.

- [ ] **Step 3: Update `jobs.py`**

Replace the full contents of `core/app/appexport/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-18a/b) : guard → (statique : gèle les
DataSources ; connecté : garde la config telle quelle + embarque l'URL du
cœur) → assemble le zip → upload S3. Tourne sur le worker partagé (queue
`appexport`, pas de Chromium/Node ici). Toute erreur marque le job "error",
jamais un job bloqué en "running" (même critère que
app.export.jobs/app.pipelines.jobs)."""
import logging
import os

from app.appexport import repository as appexport_repo
from app.appexport.bundler import build_bundle_zip
from app.appexport.freeze import freeze_config
from app.appexport.guard import check_export_guard
from app.auth.dependency import is_appexport_enabled
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _prepare_bundle_inputs(
    session, *, tenant_id: str, mode: str, config: BuilderConfig,
) -> tuple[BuilderConfig, dict | None]:
    if mode == "connected":
        core_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
        return config, {"coreUrl": core_url}
    return freeze_config(session, tenant_id=tenant_id, config=config), None


@app.task(queue="appexport")
def build_app_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_appexport_enabled():
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error="app export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        appexport_repo.mark_running(session, job_id=job_id)
        item_id = job.item_id
        mode = job.mode

    try:
        with request_scoped_session(session_factory) as session:
            config_read = configs_repo.get_config_by_item(session, item_id)
            if config_read is None:
                raise ValueError(f"app export item '{item_id}' not found")
            guard_result = check_export_guard(session, tenant_id=tenant_id, config=config_read.config, mode=mode)
            if not guard_result.allowed:
                raise ValueError("; ".join(guard_result.reasons))
            bundle_config, connection = _prepare_bundle_inputs(
                session, tenant_id=tenant_id, mode=mode, config=config_read.config,
            )

        runtime_dir = os.environ["APPEXPORT_RUNTIME_DIR"]
        zip_bytes = build_bundle_zip(bundle_config, runtime_dir=runtime_dir, connection=connection)

        result_key = f"appexports/{job_id}.zip"
        bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        s3_client = s3_client_from_env()
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(Bucket=bucket, Key=result_key, Body=zip_bytes, ContentType="application/zip")

        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("app export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/jobs.py core/tests/test_appexport_jobs.py
git commit -m "feat(core): app export job branches on mode — connected skips freezing (SP-18b)"
```

---

