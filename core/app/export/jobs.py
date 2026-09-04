# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-17a) : rend une page runtime du shell en PNG/PDF
via Chromium headless. Tourne dans le conteneur export-worker dédié (queue
`export`, jamais le worker partagé — image trop lourde pour lui, cf. design
§Infrastructure). Toute erreur marque le job "error", jamais un job bloqué
en "running" (même critère qu'app.pipelines.jobs.run_pipeline_task)."""

import logging
import os
from urllib.parse import quote

from app.auth.dependency import is_export_enabled
from app.auth.export_tokens import mint_export_token
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.rendering import RenderPage, render_export
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.notifications import repository as notifications_repo

logger = logging.getLogger(__name__)

_CONTENT_TYPE = {"png": "image/png", "pdf": "application/pdf"}


def _notify(
    session_factory,
    *,
    tenant_id: str,
    item_id: str,
    user_id: str,
    page_id: str | None,
    resource_type: str | None,
    status: str,
    error: str | None = None,
) -> None:
    """Écrit la notification in-app de fin d'export — best-effort, jamais
    bloquant : son propre bloc try/except, séparé de celui qui commite
    mark_done/mark_error, pour qu'un échec ici ne fasse jamais rollback d'un
    changement de statut de job déjà réussi (même patron que
    app.ingestion.tasks._notify et app.pipelines.jobs._notify, SP-39).

    Garde anti-double-notification : un job dont `page_id` est renseigné est
    un rendu interne au sweep de rapports (app/reports/jobs.py:153) — il sera
    notifié comme kind="report" par _notify_pending_reports (Tâche 8), jamais
    ici (spec §3.1).

    Sur le chemin d'échec, `resource_type` vaut None (le `config` qui porte
    `.kind` n'est chargé que dans le bloc `try`, indisponible dans le
    `except`) — repli sur `item.resourceType` (revue finale SP-39, I3) : sans
    ça, une notification d'échec d'export était la seule des 5 sortes jamais
    cliquable, même quand l'item existe toujours et que
    `NotificationBell.tsx` aurait pu la rendre cliquable (elle rend un
    `<div>` non cliquable dès que `item_resource_type` est None)."""
    if page_id is not None:
        return
    try:
        with request_scoped_session(session_factory) as session:
            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
            title = item.title if item is not None else item_id
            resolved_resource_type = resource_type or (
                item.resourceType if item is not None else None
            )
            notifications_repo.create_notification(
                session,
                tenant_id=tenant_id,
                recipient_user_id=user_id,
                kind="export",
                status=status,
                item_id=item_id,
                item_resource_type=resolved_resource_type,
                item_title=title,
                error_message=error,
            )
    except Exception:
        logger.exception("export job : échec de l'écriture de la notification")


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def s3_client_from_env():
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


# export_repo.reclaim_stuck_jobs (un job "running" trop vieux — export-worker
# ou Chromium tué en cours de rendu) est appelé à la fin de chaque tick de
# app.reports.jobs._trigger_due_reports depuis SP-17b, comme
# run_pipeline_sweep_task le fait pour app.pipelines.
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
        page_id, ctx = job.page_id, job.ctx

    try:
        with request_scoped_session(session_factory) as session:
            config = configs_repo.get_config_by_item(session, item_id)
            if config is None:
                raise ValueError(f"export item '{item_id}' not found")
            print_layout = config.config.printLayout

        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        base = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}"
        if page_id:
            base = f"{base}/{quote(page_id, safe='')}"
        target_url = f"{base}?exportToken={token}&exportRender=1"
        if ctx:
            target_url = f"{target_url}&ctx={ctx}"

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
        bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
        s3_client = s3_client_from_env()
        # Sur un MinIO tout neuf, "geostudio-exports" n'existe pas encore —
        # contrairement à app/ingestion/routes.py, app/cdc/storage.py et
        # app/items/storage.py, ce module appelait put_object directement,
        # échouant en NoSuchBucket au premier export (revue finale SP-17a,
        # I2). ensure_uploads_bucket est agnostique du nom de bucket malgré
        # son nom — vérifié en lisant son implémentation.
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(
            Bucket=bucket,
            Key=result_key,
            Body=content,
            ContentType=_CONTENT_TYPE[export_format],
        )
        with request_scoped_session(session_factory) as session:
            export_repo.mark_done(session, job_id=job_id, result_key=result_key)
        _notify(
            session_factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            page_id=page_id,
            resource_type="map" if config.kind == "map" else "app",
            status="success",
        )
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            export_repo.mark_error(session, job_id=job_id, error=str(exc))
        _notify(
            session_factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            page_id=page_id,
            resource_type=None,
            status="failure",
            error=str(exc),
        )
