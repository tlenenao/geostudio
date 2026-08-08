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
    # >=32 bytes: avoids PyJWT's InsecureKeyLengthWarning for HS256, which
    # this repo's `filterwarnings = ["error", ...]` (pyproject.toml) promotes
    # to a hard exception — same fix already applied in test_export_tokens.py
    # and test_auth_export_token.py (Task 4) for the same reason.
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret-padding-01234")
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


class _FakeBrowser:
    def close(self) -> None:
        pass


class _FakeContext:
    def __init__(self) -> None:
        self.browser = _FakeBrowser()


class _FakePage:
    def __init__(self) -> None:
        # render_export_task closes via browser_page.context.browser.close()
        # (mirrors a real playwright.sync_api.Page) — see the brief's note on
        # Step 4: adapt the fake rather than removing the real close call.
        self.context = _FakeContext()

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

    # Sessions distinctes (le job tourne via une session interne créée
    # par render_export_task) : avec expire_on_commit=False, le `job`
    # local est resté en cache dans l'identity map de cette session au
    # statut "pending" ; sans expire_all(), get_job() renverrait ce
    # même objet Python périmé plutôt que l'état réellement écrit en base
    # (comportement par défaut de SQLAlchemy pour un objet déjà chargé).
    session.expire_all()
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

    # Sessions distinctes (le job tourne via une session interne créée
    # par render_export_task) : avec expire_on_commit=False, le `job`
    # local est resté en cache dans l'identity map de cette session au
    # statut "pending" ; sans expire_all(), get_job() renverrait ce
    # même objet Python périmé plutôt que l'état réellement écrit en base
    # (comportement par défaut de SQLAlchemy pour un objet déjà chargé).
    session.expire_all()
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

    # Sessions distinctes (le job tourne via une session interne créée
    # par render_export_task) : avec expire_on_commit=False, le `job`
    # local est resté en cache dans l'identity map de cette session au
    # statut "pending" ; sans expire_all(), get_job() renverrait ce
    # même objet Python périmé plutôt que l'état réellement écrit en base
    # (comportement par défaut de SQLAlchemy pour un objet déjà chargé).
    session.expire_all()
    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"
    assert "navigation timeout" in refreshed.error


def test_render_export_task_missing_job_is_a_noop(db_session):
    session, tenant, _user, _item = db_session
    export_jobs.render_export_task(job_id="does-not-exist", tenant_id=tenant.id)  # ne doit pas lever


import http.server
import socket
import threading


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
            # Must also stop the driver, not just close the browser: see the
            # leak comment in app/export/jobs.py::_launch_and_navigate — an
            # earlier version of this test (browser.close() only) corrupted
            # anyio's cached test Runner for every async test that ran
            # afterward in the same pytest session.
            page._geostudio_playwright.stop()
    finally:
        server.shutdown()
