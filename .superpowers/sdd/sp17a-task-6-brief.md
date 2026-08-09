### Task 6: Job procrastinate `render_export_task`

**Files:**
- Create: `core/app/export/jobs.py`
- Modify: `core/pyproject.toml` (dépendance `playwright`)
- Test: `core/tests/test_export_jobs.py`

**Interfaces:**
- Consumes: `export_repo.{get_job,mark_running,mark_done,mark_error}` (Tâche 3), `render_export` (Tâche 5), `mint_export_token` (Tâche 4), `configs_repo.get_config_by_item` (existant), `is_export_enabled` (Tâche 2).
- Produces: `render_export_task(job_id: str, tenant_id: str)` — tâche `@app.task(queue="export")`, jamais de job zombie (toute exception → `mark_error`). `_launch_and_navigate(url: str) -> RenderPage` — factorisée seule pour être monkeypatchable en test (seul point qui a besoin d'un vrai navigateur).

- [ ] **Step 1: Ajouter la dépendance Playwright**

Dans `core/pyproject.toml`, dans `dependencies = [...]`, ajouter après `"openpyxl>=3.1", ...` (avant les lignes `opentelemetry-*`) :

```toml
    "playwright>=1.45",  # SP-17a : rendu headless Chromium pour l'export
                        # PNG/PDF (app/export/jobs.py) — installé sans le
                        # binaire navigateur par défaut ; `playwright install
                        # --with-deps chromium` est requis en plus (fait dans
                        # le Dockerfile export-worker, tâche 13 ; à faire à la
                        # main en dev local pour lancer les tests marqués
                        # @pytest.mark.playwright de cette tâche).
```

Run : `cd core && uv sync`
Expected: `playwright` installé dans l'environnement (pas encore le binaire Chromium — normal, seul le test `@pytest.mark.playwright` en a besoin, guardé et skippable, cf. Step 6).

- [ ] **Step 2: Écrire le test qui échoue (orchestration, sans navigateur réel)**

```python
# core/tests/test_export_jobs.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import jobs as export_jobs
from app.export import repository as export_repo
from app.items.repository import create_item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def export_env(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")
    monkeypatch.setenv("SHELL_BASE_URL", "http://shell.test")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    db_path = tmp_path / "export_jobs.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="Alice", last_name="", bootstrap_admin=False,
    )
    item = create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="Carte test")
    configs_repo.create_config(
        session,
        BuilderConfig(kind="map", map={"basemap": {"style": "https://x.test/s.json"}, "view": {"center": [0.0, 0.0], "zoom": 2.0}}),
        item.id, tenant_id=tenant.id,
    )
    session.commit()
    return session, tenant, user, item


class _FakePage:
    def screenshot(self, *, full_page: bool) -> bytes:
        return b"PNGDATA"

    def pdf(self, *, format: str, landscape: bool) -> bytes:
        return b"PDFDATA"


def test_render_export_task_marks_done_on_success(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    uploaded = {}

    class _FakeS3Client:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            uploaded["bucket"] = Bucket
            uploaded["key"] = Key
            uploaded["body"] = Body

        def generate_presigned_url(self, *args, **kwargs):
            return "https://minio.test/presigned"

    monkeypatch.setattr(export_jobs, "_s3_client_from_env", lambda: _FakeS3Client())

    # Appel direct de la fonction tâche (pas .defer() + run_worker) : teste
    # l'orchestration synchrone, pas la file — pas besoin d'InMemoryConnector
    # ici (contrairement à core/tests/test_alert_jobs.py qui teste, lui, le
    # vrai chemin .defer()/run_worker).
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "done"
    assert refreshed.result_key is not None
    assert uploaded["bucket"] == "geostudio-exports"
    assert uploaded["body"] == b"PNGDATA"


def test_render_export_task_marks_error_when_export_disabled(db_session, monkeypatch):
    session, tenant, user, item = db_session
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"


def test_render_export_task_marks_error_never_zombie_on_navigation_failure(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    def _boom(url):
        raise RuntimeError("navigation timeout")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"
    assert "navigation timeout" in refreshed.error


def test_render_export_task_missing_job_is_a_noop(db_session):
    session, tenant, _user, _item = db_session
    export_jobs.render_export_task(job_id="does-not-exist", tenant_id=tenant.id)  # ne doit pas lever
```

- [ ] **Step 3: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.jobs'`

- [ ] **Step 4: Implémenter**

```python
# core/app/export/jobs.py
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-17a) : rend une page runtime du shell en PNG/PDF
via Chromium headless. Tourne dans le conteneur export-worker dédié (queue
`export`, jamais le worker partagé — image trop lourde pour lui, cf. design
§Infrastructure). Toute erreur marque le job "error", jamais un job bloqué
en "running" (même critère qu'app.pipelines.jobs.run_pipeline_task)."""
import logging
import os

from app.auth.dependency import is_export_enabled
from app.auth.export_tokens import mint_export_token
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.rendering import RenderPage, render_export
from app.ingestion.storage import generate_presigned_get_url, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)

_CONTENT_TYPE = {"png": "image/png", "pdf": "application/pdf"}


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _launch_and_navigate(url: str) -> RenderPage:
    # Seule fonction de ce module qui a besoin d'un vrai Chromium — isolée
    # pour être monkeypatchée en test (cf. tests/test_export_jobs.py). Pas de
    # gestion de cycle de vie du navigateur ici au-delà de la navigation :
    # la tâche appelante ferme tout dans un `finally` (cf. render_export_task).
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_selector('[data-export-ready="true"]', timeout=30_000, state="attached")
    return page


@app.task(queue="export")
def render_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_export_enabled():
        with request_scoped_session(session_factory) as session:
            export_repo.mark_error(session, job_id=job_id, error="export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        export_repo.mark_running(session, job_id=job_id)
        item_id, user_id, export_format = job.item_id, job.user_id, job.format

    try:
        with request_scoped_session(session_factory) as session:
            config = configs_repo.get_config_by_item(session, item_id)
            if config is None:
                raise ValueError(f"export item '{item_id}' not found")
            print_layout = config.config.printLayout

        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        target_url = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}?exportToken={token}&exportRender=1"

        browser_page = _launch_and_navigate(target_url)
        try:
            content = render_export(browser_page, format=export_format, print_layout=print_layout)
        finally:
            browser_page.context.browser.close()

        result_key = f"renders/{job_id}.{export_format}"
        _s3_client_from_env().put_object(
            Bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
            Key=result_key, Body=content, ContentType=_CONTENT_TYPE[export_format],
        )
        with request_scoped_session(session_factory) as session:
            export_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            export_repo.mark_error(session, job_id=job_id, error=str(exc))
```

Note : `browser_page.context.browser.close()` suppose que `_launch_and_navigate` renvoie un vrai `playwright.sync_api.Page` en production (dont `.context.browser` existe) ; le `_FakePage` de test n'a pas cet attribut — c'est voulu, les tests d'orchestration (Step 2) ne passent jamais par ce chemin de fermeture puisqu'ils monkeypatchent `_launch_and_navigate` pour renvoyer un objet minimal AVANT le `try/finally` de fermeture. Si un test échoue sur `AttributeError` à la fermeture, adapter `_FakePage` pour exposer un `context.browser.close()` factice plutôt que de retirer l'appel réel.

- [ ] **Step 5: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Test guardé avec un vrai navigateur (best-effort, non bloquant)**

```python
# core/tests/test_export_jobs.py (ajouter à la suite)
import http.server
import socket
import threading

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.playwright
def test_launch_and_navigate_real_chromium_waits_for_export_ready(tmp_path):
    pytest.importorskip("playwright")
    (tmp_path / "index.html").write_text(
        '<html><body><script>setTimeout(() => { document.body.dataset.exportReady = "true"; }, 200);</script></body></html>'
    )
    port = _free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from app.export.jobs import _launch_and_navigate

        page = _launch_and_navigate(f"http://127.0.0.1:{port}/index.html")
        try:
            assert page.screenshot(full_page=True)
        finally:
            page.context.browser.close()
    finally:
        server.shutdown()
```

Run : `cd core && uv run playwright install --with-deps chromium && uv run pytest tests/test_export_jobs.py -v -m playwright`
Expected : PASS si Chromium peut s'installer dans cet environnement — **sinon SKIP proprement** (marqueur `@pytest.mark.playwright`, à enregistrer dans `core/pyproject.toml` `[tool.pytest.ini_options] markers` s'il existe une section de ce type, sinon dans `core/pytest.ini`/`conftest.py`). Si `playwright install` échoue faute de `sudo`/accès réseau dans cet environnement (risque déjà rencontré pour le sidecar QGIS, SP-15d), **documenter cet état exact dans le rapport de tâche** plutôt que de prétendre qu'il a tourné — ce test guardé n'est pas bloquant pour la suite du plan, toute la logique d'orchestration (Step 2) est déjà vérifiée sans navigateur réel.

- [ ] **Step 7: Commit**

```bash
git add core/app/export/jobs.py core/pyproject.toml core/tests/test_export_jobs.py core/uv.lock
git commit -m "feat(core): SP-17a — tâche procrastinate render_export_task"
```

---

