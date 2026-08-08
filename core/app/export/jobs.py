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
    # pour être monkeypatchée en test (cf. tests/test_export_jobs.py). La
    # tâche appelante ferme la page/le navigateur retournés dans un
    # `finally` (cf. render_export_task) — mais ça ne couvre que le cas où
    # cette fonction *réussit*. Si driver start / chromium.launch / new_page
    # / goto / wait_for_selector échoue en cours de route, tout ce qui a
    # déjà été créé (processus driver Node, processus Chromium) doit être
    # nettoyé ici même, avant de relayer l'exception — sinon ça fuit
    # silencieusement à chaque échec, sans jamais atteindre le `finally`
    # de l'appelant (revue SP-17a task 6, fix round 1).
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = None
    try:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="load")
        page.wait_for_selector('[data-export-ready="true"]', timeout=30_000, state="attached")
    except Exception:
        try:
            if browser is not None:
                browser.close()
        finally:
            playwright.stop()
        raise

    # sync_playwright().start() without a matching .stop() leaks the driver
    # connection and the asyncio event loop it privately owns (confirmed:
    # running a real-Chromium call inside the pytest suite without stopping
    # it corrupts anyio's cached test Runner for every async test that runs
    # afterward in the same process — "RuntimeError: Runner is closed"). In
    # production this would leak a Node driver subprocess per export job on
    # a long-running worker. Stash the handle on the page (regular object,
    # no __slots__) so the caller can stop it alongside browser.close() —
    # keeps this function's return type exactly RenderPage, no signature
    # change needed for the monkeypatched orchestration tests.
    page._geostudio_playwright = playwright
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
            # See the comment in _launch_and_navigate: closing the browser
            # alone does not stop the Playwright driver connection/loop.
            # _FakePage (orchestration tests) never sets this attribute, so
            # getattr()'s default keeps those tests a real no-op here.
            # Nested try/finally (not a flat pair of statements): if
            # browser.close() itself raises, the driver stop must still run
            # — a flat sequence would let a close() failure skip it, leaking
            # the driver process (revue SP-17a task 6, fix round 1, Minor).
            playwright_driver = getattr(browser_page, "_geostudio_playwright", None)
            try:
                browser_page.context.browser.close()
            finally:
                if playwright_driver is not None:
                    playwright_driver.stop()

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
