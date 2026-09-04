# SPDX-License-Identifier: Apache-2.0
import http.server
import socket
import threading

import pytest
from sqlalchemy import select

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import jobs as export_jobs
from app.export import repository as export_repo
from app.items.repository import create_item
from app.notifications.models import Notification
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
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="Alice",
        last_name="",
        bootstrap_admin=False,
    )
    item = create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="Carte test"
    )
    configs_repo.create_config(
        session,
        BuilderConfig(
            kind="map",
            map={
                "basemap": {"style": "https://x.test/s.json"},
                "view": {"center": [0.0, 0.0], "zoom": 2.0},
            },
        ),
        item.id,
        tenant_id=tenant.id,
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

    def pdf(self, **kwargs) -> bytes:
        # **kwargs (not a fixed display_header_footer/footer_template
        # signature) mirrors RenderPage.pdf's evolving kwarg set (SP-17b
        # Task 5 added display_header_footer/footer_template on top of
        # format/landscape/print_background) without needing another edit
        # here next time it grows — see test_export_rendering.py's _FakePage
        # for the same convention.
        self.pdf_kwargs = kwargs
        return b"PDFDATA"


class _FakeUploadS3Client:
    """Minimal S3 fake for tests that only care about the render/URL path,
    not upload details — render_export_task always uploads after a
    successful render, so any test asserting status == "done" needs this
    (or a real MinIO) or it fails downstream with EndpointConnectionError
    against the unreachable http://minio.test placeholder, for a reason
    unrelated to what the test is actually exercising."""

    def create_bucket(self, *, Bucket):
        pass

    def put_bucket_cors(self, *, Bucket, CORSConfiguration):
        pass

    def put_object(self, *, Bucket, Key, Body, ContentType):
        pass

    def generate_presigned_url(self, *args, **kwargs):
        return "https://minio.test/presigned"


def test_render_export_task_marks_done_on_success(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    uploaded = {}
    calls = []

    class _FakeS3Client:
        # I2 (revue finale) : render_export_task doit s'assurer que le bucket
        # existe (ensure_uploads_bucket) AVANT put_object — sur un MinIO
        # tout neuf, put_object seul échouerait en NoSuchBucket. `calls`
        # trace l'ordre pour le prouver, pas seulement l'appel.
        def create_bucket(self, *, Bucket):
            calls.append(("create_bucket", Bucket))

        def put_bucket_cors(self, *, Bucket, CORSConfiguration):
            calls.append(("put_bucket_cors", Bucket))

        def put_object(self, *, Bucket, Key, Body, ContentType):
            calls.append(("put_object", Bucket))
            uploaded["bucket"] = Bucket
            uploaded["key"] = Key
            uploaded["body"] = Body

        def generate_presigned_url(self, *args, **kwargs):
            return "https://minio.test/presigned"

    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeS3Client())

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
    # Le bucket doit être créé (via ensure_uploads_bucket) AVANT l'upload —
    # pas seulement appelé quelque part.
    assert [c[0] for c in calls] == ["create_bucket", "put_bucket_cors", "put_object"]
    assert all(c[1] == "geostudio-exports" for c in calls)


def test_render_export_task_marks_error_when_export_disabled(db_session, monkeypatch):
    session, tenant, user, item = db_session
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
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
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
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


def test_render_export_task_builds_url_with_page_id_and_ctx(db_session, monkeypatch):
    session, tenant, user, item = db_session
    captured_urls = []

    def fake_launch_and_navigate(url):
        captured_urls.append(url)
        return _FakePage()

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", fake_launch_and_navigate)
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        user_id=user.id,
        format="pdf",
        page_id="page-2",
        ctx="abc123",
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    # db_session's item is a "map" config (kind="map"), so route == "maps"
    # (see render_export_task's `route = "maps" if config.kind == "map" ...`)
    # — not "apps" as in the brief's illustrative (app) example.
    assert len(captured_urls) == 1
    assert f"/maps/{item.id}/page-2?exportToken=" in captured_urls[0]
    assert captured_urls[0].endswith("&ctx=abc123")

    # Guards against a regression where the PDF render itself blows up after
    # the URL is already captured (e.g. _FakePage.pdf() rejecting a kwarg
    # RenderPage.pdf now requires) — the exception would be swallowed by
    # render_export_task's catch-all and silently flip the job to "error"
    # while this test kept asserting green on captured_urls alone.
    session.expire_all()
    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "done"


def test_render_export_task_url_unchanged_when_page_id_and_ctx_absent(db_session, monkeypatch):
    session, tenant, user, item = db_session
    captured_urls = []
    monkeypatch.setattr(
        export_jobs,
        "_launch_and_navigate",
        lambda url: captured_urls.append(url) or _FakePage(),
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    assert len(captured_urls) == 1
    assert f"/maps/{item.id}?exportToken=" in captured_urls[0]
    assert "ctx=" not in captured_urls[0]

    # See the identical comment in
    # test_render_export_task_builds_url_with_page_id_and_ctx: without this,
    # a broken _FakePage.pdf() would still leave this test green.
    session.expire_all()
    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "done"


def test_render_export_task_missing_job_is_a_noop(db_session):
    session, tenant, _user, _item = db_session
    export_jobs.render_export_task(
        job_id="does-not-exist", tenant_id=tenant.id
    )  # ne doit pas lever


class _FakeLaunchedBrowser:
    """Navigateur "lancé avec succès" mais dont la suite de la séquence
    échoue (new_page/goto/wait_for_selector) — utilisé pour prouver que
    _launch_and_navigate ferme ce qu'elle a déjà créé avant de relayer
    l'exception (fix round 1 : revue SP-17a task 6, fuite Chromium/driver
    sur échec de lancement)."""

    def __init__(self) -> None:
        self.closed = False

    def new_page(self):
        raise RuntimeError("boom: new_page a échoué après le lancement du navigateur")

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeLaunchedBrowser) -> None:
        self._browser = browser

    def launch(self, headless: bool):
        return self._browser


class _FakePlaywrightDriver:
    """Fait à la fois office de valeur de retour de sync_playwright().start()
    (a un attribut .chromium) et de driver arrêtable (a une méthode .stop()) —
    reflète exactement l'objet réel de playwright.sync_api."""

    def __init__(self, browser: _FakeLaunchedBrowser) -> None:
        self.chromium = _FakeChromium(browser)
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeSyncPlaywrightContextManager:
    def __init__(self, driver: _FakePlaywrightDriver) -> None:
        self._driver = driver

    def start(self):
        return self._driver


def test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure(monkeypatch):
    # Reproduit le vrai trou signalé en revue : contrairement à
    # test_render_export_task_marks_error_never_zombie_on_navigation_failure
    # (qui mocke _launch_and_navigate entièrement et ne prouve donc que le
    # statut du job), ce test laisse le vrai corps de _launch_and_navigate
    # s'exécuter et ne fait échouer qu'une étape interne
    # (browser.new_page()), après que le driver et le navigateur ont déjà
    # été créés — pour prouver que les deux sont bien nettoyés plutôt que
    # fuités quand l'exception remonte.
    browser = _FakeLaunchedBrowser()
    driver = _FakePlaywrightDriver(browser)
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _FakeSyncPlaywrightContextManager(driver),
    )

    with pytest.raises(RuntimeError, match="boom"):
        export_jobs._launch_and_navigate("http://shell.test/maps/x")

    assert browser.closed is True
    assert driver.stopped is True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.playwright
def test_launch_and_navigate_real_chromium_waits_for_export_ready(tmp_path, chromium_available):
    (tmp_path / "index.html").write_text(
        "<html><body><script>"
        'setTimeout(() => { document.body.dataset.exportReady = "true"; }, 200);'
        "</script></body></html>"
    )
    port = _free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path)),
    )
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


def test_success_writes_a_notification_for_the_requester(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is not None
    assert notification.recipient_user_id == user.id
    assert notification.kind == "export"
    assert notification.status == "success"
    assert notification.item_resource_type == "map"
    assert notification.item_title == "Carte test"


def test_failure_writes_a_notification(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()

    def _boom(url):
        raise RuntimeError("navigation timeout")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is not None
    assert notification.status == "failure"
    assert "navigation timeout" in notification.error_message


def test_report_triggered_export_does_not_write_an_export_notification(db_session, monkeypatch):
    """job.page_id renseigné == rendu interne au sweep de rapports — la
    notification sera écrite comme kind="report" par _notify_pending_reports
    (Tâche 8), jamais ici (sinon double notification pour le même événement,
    cf. spec §3.1)."""
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        user_id=user.id,
        format="pdf",
        page_id="page-1",
    )
    session.commit()
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is None
