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
from app.notifications import repository as notifications_repo
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
        self.incomplete = False

    def evaluate(self, expression: str):
        return "true" if self.incomplete else None

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

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: _FakePage())
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
    # SP-58 Tâche 2 (GAP-73) : la taille du rendu écrit sur S3 doit être
    # tracée pour permettre la mesure de stockage par tenant (le bucket
    # geostudio-exports n'est pas préfixé par tenant_id, cf. spec §1.4).
    assert refreshed.byte_size == len(b"PNGDATA")
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


def test_render_export_task_fails_when_shell_flags_export_incomplete(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
    )
    session.commit()
    page = _FakePage()
    page.incomplete = True
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: page)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    session.expire_all()
    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"
    assert refreshed.error == export_jobs.USER_EXPORT_INCOMPLETE
    assert not hasattr(page, "pdf_kwargs")  # rien n'a été rendu


def test_render_export_task_marks_error_never_zombie_on_navigation_failure(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()

    def _boom(url, **kw):
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

    def fake_launch_and_navigate(url, **kw):
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
    assert f"/maps/{item.id}/page-2?exportRender=1" in captured_urls[0]
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
        lambda url, **kw: captured_urls.append(url) or _FakePage(),
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    assert len(captured_urls) == 1
    assert f"/maps/{item.id}?exportRender=1" in captured_urls[0]
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

    def new_page(self, **kw):
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


class _Req:
    def __init__(self, url):
        self.url = url


class _Route:
    def __init__(self, url):
        self.request = _Req(url)
        self.outcome = None

    def continue_(self):
        self.outcome = "continue"

    def abort(self, reason="failed"):
        self.outcome = f"abort:{reason}"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://shell.test/assets/app.js", "continue"),
        ("https://geo.example/api/v1/items", "continue"),
        ("data:image/png;base64,AAAA", "continue"),
        ("http://169.254.169.254/opc/v2/instance/", "abort:blockedbyclient"),
        ("http://minio:9000/bucket/x", "abort:blockedbyclient"),
        ("http://[64:ff9b::a9fe:a9fe]/", "abort:blockedbyclient"),
        ("file:///etc/passwd", "abort:blockedbyclient"),
        ("https://8.8.8.8/tiles/1/2/3.png", "continue"),
    ],
)
def test_egress_route_handler_blocks_internal_targets(monkeypatch, url, expected):
    real = socket.getaddrinfo
    monkeypatch.delenv("CORE_EXPORT_EGRESS_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: (
            [(0, 0, 0, "", ("172.18.0.5", 0))] if host == "minio" else real(host, *a, **k)
        ),
    )
    handler = export_jobs._egress_route_handler(
        frozenset({"http://shell.test", "https://geo.example"})
    )
    route = _Route(url)
    handler(route)
    assert route.outcome == expected


def test_render_url_no_longer_carries_the_token(db_session, monkeypatch):
    session, tenant, user, item = db_session
    urls, tokens = [], []
    monkeypatch.setattr(
        export_jobs,
        "_launch_and_navigate",
        lambda url, **kw: urls.append(url) or tokens.append(kw.get("export_token")) or _FakePage(),
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    assert "exportToken" not in urls[0]
    assert "exportRender=1" in urls[0]
    assert tokens[0]


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
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: _FakePage())
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

    def _boom(url, **kw):
        raise RuntimeError("navigation timeout")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is not None
    assert notification.status == "failure"
    assert "navigation timeout" in notification.error_message
    # Revue finale SP-39 (I3) : resource_type vaut None dans la branche
    # d'échec (config non chargé), mais l'item existe toujours — la
    # notification doit rester cliquable (repli sur item.resourceType),
    # pas la seule des 5 sortes de notification jamais cliquable.
    assert notification.item_resource_type == "map"


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
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is None


def test_notification_write_failure_does_not_affect_job_status(db_session, monkeypatch):
    """I2 (revue finale SP-39) : une erreur dans l'écriture de la
    notification ne doit jamais affecter le statut du job lui-même. Boom
    réel (viole une contrainte NOT NULL, SAWarning-as-error sous pytest ou
    IntegrityError hors pytest) plutôt qu'une exception Python qui ne
    toucherait jamais la session — cf. test_report_jobs.py pour la même
    falsification."""
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: _FakePage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())

    def _boom(session, **kwargs):
        session.add(
            Notification(
                tenant_id=tenant.id,
                recipient_user_id=user.id,
                kind="x",
                status="failure",
                item_title="x",
            )
        )
        session.flush()

    monkeypatch.setattr(notifications_repo, "create_notification", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    session.expire_all()  # cf. test_render_export_task_marks_done_on_success pour la raison
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "done"
    notification = session.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
    assert notification is None


def test_render_export_task_handles_get_job_failure_gracefully(db_session, monkeypatch):
    # GAP-56.1 (SP-49) : get_job/mark_running étaient hors du bloc try — une
    # exception ici remontait non gérée (pas de mark_error, pas de
    # notification), contrairement à app.pipelines.jobs/app.ingestion.tasks
    # qui placent ces deux appels DANS le try. Falsifié en session (avant
    # correction, ce test échouait avec la RuntimeError non capturée plutôt
    # que de constater job.status == "error").
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()

    original_get_job = export_repo.get_job
    calls = {"n": 0}

    def _boom(session, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return original_get_job(session, **kwargs)

    monkeypatch.setattr(export_repo, "get_job", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    session.expire_all()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert "db down" in fetched.error


def _serve_env_config(tmp_path, core_url: str):
    (tmp_path / "env-config.js").write_text(
        f'window.__GEOSTUDIO_ENV__ = {{\n  VITE_CORE_URL: "{core_url}",\n}};\n'
    )
    port = _free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def test_core_unreachable_error_names_the_cause(tmp_path):
    # j05b-006 : VITE_CORE_URL=localhost:<port fermé> vu depuis export-worker.
    server, shell_url = _serve_env_config(tmp_path, f"http://127.0.0.1:{_free_port()}")
    try:
        message = export_jobs.core_unreachable_error(shell_url)
    finally:
        server.shutdown()
    assert message is not None and "VITE_CORE_URL" in message and "export-worker" in message


def test_core_unreachable_error_none_when_core_answers(tmp_path):
    core, core_url = _serve_env_config(tmp_path, "unused")  # répond 404 sur /health : joignable
    shell, shell_url = _serve_env_config(tmp_path, core_url)
    try:
        assert export_jobs.core_unreachable_error(shell_url) is None
    finally:
        core.shutdown()
        shell.shutdown()


def test_render_export_task_fails_fast_when_core_unreachable(db_session, monkeypatch, tmp_path):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    server, shell_url = _serve_env_config(tmp_path, f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("SHELL_BASE_URL", shell_url)
    monkeypatch.delenv("EXPORT_CORE_INTERNAL_URL", raising=False)

    def _must_not_launch(url):
        raise AssertionError("Chromium ne doit pas être lancé")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _must_not_launch)
    try:
        export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    finally:
        server.shutdown()

    session.expire_all()
    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"
    assert "administrateur" in refreshed.error


# ARC-16 : annulation, viewport à la taille de la feuille, budget de 120 s.
def _job(db_session, fmt="pdf"):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format=fmt
    )
    session.commit()
    return job


def _status(db_session, job):
    session, tenant, _u, _i = db_session
    session.expire_all()
    return export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id).status


def test_cancel_requested_before_launch_never_starts_chromium(db_session, monkeypatch):
    session, tenant, _u, _i = db_session
    job = _job(db_session)
    launched = []
    monkeypatch.setattr(
        export_jobs, "_launch_and_navigate", lambda url, **kw: launched.append(url) or _FakePage()
    )
    # annulation demandée juste après mark_running
    real = export_repo.mark_running

    def mark_then_cancel(s, *, job_id):
        ok = real(s, job_id=job_id)
        export_repo.request_cancel(s, job_id=job_id)
        return ok

    monkeypatch.setattr(export_repo, "mark_running", mark_then_cancel)
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert launched == []
    assert _status(db_session, job) == "cancelled"


def test_cancel_requested_during_render_skips_the_upload(db_session, monkeypatch):
    session, tenant, _u, _i = db_session
    job = _job(db_session)

    class _CancellingPage(_FakePage):
        def pdf(self, **kwargs):
            with export_jobs.request_scoped_session(export_jobs.session_factory()) as s:
                export_repo.request_cancel(s, job_id=job.id)
            return b"PDFDATA"

    uploads = []

    class _S3(_FakeUploadS3Client):
        def put_object(self, **kw):
            uploads.append(kw)

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url, **kw: _CancellingPage())
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _S3())
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert uploads == []
    assert _status(db_session, job) == "cancelled"


def test_render_viewport_matches_the_sheet(db_session, monkeypatch):
    session, tenant, user, _item = db_session
    item = create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="A3"
    )
    configs_repo.create_config(
        session,
        BuilderConfig(
            kind="map",
            map={
                "basemap": {"style": "https://x.test/s.json"},
                "view": {"center": [0.0, 0.0], "zoom": 2.0},
            },
            printLayout={"pageSize": "a3", "orientation": "landscape"},
        ),
        item.id,
        tenant_id=tenant.id,
    )
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    seen = {}
    monkeypatch.setattr(
        export_jobs,
        "_launch_and_navigate",
        lambda url, viewport=None, **kw: seen.update(viewport=viewport) or _FakePage(),
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert seen["viewport"] == (1587, 1123)


def test_launch_and_navigate_shares_one_120s_budget(monkeypatch):
    calls = {}

    class _Page:
        context = None

        def goto(self, url, wait_until, timeout):
            calls["goto"] = timeout

        def wait_for_selector(self, sel, timeout, state):
            calls["wait"] = timeout

        def set_default_timeout(self, ms):
            calls["default"] = ms

        def route(self, pattern, handler):
            calls.setdefault("routes", []).append(pattern)

        def add_init_script(self, script):
            calls["init"] = script

    class _Browser:
        def new_page(self, **kw):
            calls["viewport"] = kw.get("viewport")
            calls["page_kw"] = kw
            return _Page()

    class _Chromium:
        def launch(self, headless):
            return _Browser()

    class _Driver:
        chromium = _Chromium()

    class _CM:
        def start(self):
            return _Driver()

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _CM())
    monkeypatch.setattr(export_jobs, "_published_core_url", lambda _: None)
    export_jobs._launch_and_navigate(
        "http://shell.test/maps/x",
        (1587, 1123),
        core_bridge=("http://localhost:8200", "http://core:8200"),
        export_token="tok",
    )
    assert calls["viewport"] == {"width": 1587, "height": 1123}
    # AUD-023 : garde réseau d'abord (le pont, enregistré après, reste prioritaire),
    # service workers bloqués (ils contourneraient page.route).
    assert calls["routes"] == ["**/*", "http://localhost:8200/**"]
    assert calls["page_kw"]["service_workers"] == "block"
    # AUD-024 : jeton posé dans sessionStorage de l'origine du shell, jamais l'URL.
    assert '"http://shell.test"' in calls["init"] and '"tok"' in calls["init"]
    assert calls["goto"] <= 120_000 and calls["wait"] <= 120_000 and calls["default"] <= 120_000
    assert calls["goto"] >= calls["wait"] >= calls["default"] > 100_000


@pytest.mark.parametrize(
    ("scope", "suffix"), [("atlas", "&atlas=1"), ("entity:a b", "&entityId=a%20b")]
)
def test_render_export_task_appends_atlas_scope(db_session, monkeypatch, scope, suffix):
    session, tenant, user, item = db_session
    urls = []
    monkeypatch.setattr(
        export_jobs, "_launch_and_navigate", lambda url, **kw: urls.append(url) or _FakePage()
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf", scope=scope
    )
    session.commit()
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert urls[0].endswith(suffix)


class _FakeRoute:
    def __init__(self, method: str, url: str, headers: dict | None = None):
        self.request = type("R", (), {"method": method, "url": url, "headers": headers or {}})()
        self.fulfilled: dict | None = None
        self.fetched_url: str | None = None

    def fetch(self, *, url):
        self.fetched_url = url
        return type("Resp", (), {"headers": {"content-type": "application/json"}})()

    def fulfill(self, **kw):
        self.fulfilled = kw


def test_core_bridge_handler_answers_preflight_without_calling_core():
    handler = export_jobs._core_bridge_handler("http://localhost:8200", "http://core:8200")
    route = _FakeRoute("OPTIONS", "http://localhost:8200/v1/me", {"origin": "http://shell:8300"})
    handler(route)
    assert route.fetched_url is None
    assert route.fulfilled["status"] == 204
    h = route.fulfilled["headers"]
    assert h["access-control-allow-origin"] == "http://shell:8300"
    assert "authorization" in h["access-control-allow-headers"]


def test_core_bridge_handler_forwards_to_internal_core_with_cors():
    handler = export_jobs._core_bridge_handler("http://localhost:8200", "http://core:8200")
    route = _FakeRoute("GET", "http://localhost:8200/v1/items?x=1", {"origin": "http://shell:8300"})
    handler(route)
    assert route.fetched_url == "http://core:8200/v1/items?x=1"
    assert route.fulfilled["headers"]["access-control-allow-origin"] == "http://shell:8300"
    assert route.fulfilled["headers"]["content-type"] == "application/json"


def test_core_bridge_target_when_public_core_down_and_internal_up(tmp_path, monkeypatch):
    internal, internal_url = _serve_env_config(tmp_path, "unused")  # 404 sur /health : joignable
    public_url = f"http://127.0.0.1:{_free_port()}"
    shell, shell_url = _serve_env_config(tmp_path, public_url)
    monkeypatch.setenv("EXPORT_CORE_INTERNAL_URL", internal_url)
    try:
        assert export_jobs.core_bridge_target(shell_url) == (public_url, internal_url)
    finally:
        internal.shutdown()
        shell.shutdown()


def test_core_bridge_target_none_when_public_core_reachable(tmp_path, monkeypatch):
    core, core_url = _serve_env_config(tmp_path, "unused")
    shell, shell_url = _serve_env_config(tmp_path, core_url)
    monkeypatch.setenv("EXPORT_CORE_INTERNAL_URL", f"http://127.0.0.1:{_free_port()}")
    try:
        assert export_jobs.core_bridge_target(shell_url) is None
    finally:
        core.shutdown()
        shell.shutdown()


def test_unreachable_core_gives_user_message_not_ops_detail(db_session, monkeypatch, tmp_path):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    server, shell_url = _serve_env_config(tmp_path, f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("SHELL_BASE_URL", shell_url)
    monkeypatch.delenv("EXPORT_CORE_INTERNAL_URL", raising=False)
    try:
        export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    finally:
        server.shutdown()
    session.expire_all()
    error = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id).error
    assert "VITE_CORE_URL" not in error and "export-worker" not in error
    assert "administrateur" in error


def test_ctx_is_url_quoted_in_target(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session,
        tenant_id=tenant.id,
        item_id=item.id,
        user_id=user.id,
        format="png",
        ctx="abc&exportToken=evil",
    )
    session.commit()
    monkeypatch.setenv("SHELL_BASE_URL", "http://shell.test")
    monkeypatch.setattr(export_jobs, "core_unreachable_error", lambda *_: None)
    monkeypatch.setattr(export_jobs, "core_bridge_target", lambda *_: None)
    seen = []
    monkeypatch.setattr(
        export_jobs, "_launch_and_navigate", lambda url, **kw: seen.append(url) or _FakePage()
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert seen and "&ctx=abc%26exportToken%3Devil" in seen[0]
    assert seen[0].count("exportToken=") == 0  # AUD-024 : plus jamais dans l'URL
