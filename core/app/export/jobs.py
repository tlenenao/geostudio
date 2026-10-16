# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-17a) : rend une page runtime du shell en PNG/PDF
via Chromium headless. Tourne dans le conteneur export-worker dédié (queue
`export`, jamais le worker partagé — image trop lourde pour lui, cf. design
§Infrastructure). Toute erreur marque le job "error", jamais un job bloqué
en "running" (même critère qu'app.pipelines.jobs.run_pipeline_task)."""

import logging
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from app.auth.dependency import is_export_enabled
from app.auth.export_tokens import mint_export_token
from app.configs import repository as configs_repo
from app.db import request_scoped_session
from app.export import repository as export_repo
from app.export.models import ExportJob
from app.export.rendering import RENDER_TIMEOUT_MS, RenderPage, page_pixels, render_export
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.jobs.common import notify_best_effort, session_factory

logger = logging.getLogger(__name__)

_CONTENT_TYPE = {"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml"}


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
    `<div>` non cliquable dès que `item_resource_type` est None).

    SP-43 Tâche 6 : l'écriture proprement dite est désormais déléguée à
    app.jobs.common.notify_best_effort — cette fonction ne garde que la
    garde anti-double-notification et la résolution titre/resource_type
    propres au domaine export (`user_id` est déjà résolu par l'appelant)."""
    if page_id is not None:
        return
    try:
        with request_scoped_session(session_factory) as session:
            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
            title = item.title if item is not None else item_id
            resolved_resource_type = resource_type or (
                item.resourceType if item is not None else None
            )
    except Exception:
        logger.exception("export job : échec de la résolution du titre de notification")
        return
    notify_best_effort(
        session_factory,
        tenant_id=tenant_id,
        recipient_user_id=user_id,
        kind="export",
        status=status,
        item_id=item_id,
        item_resource_type=resolved_resource_type,
        item_title=title,
        error=error,
    )


def _cancelled(factory, job_id: str) -> bool:
    """True (et statut final `cancelled`) si l'annulation a été demandée."""
    with request_scoped_session(factory) as session:
        if not export_repo.is_cancel_requested(session, job_id=job_id):
            return False
        export_repo.mark_cancelled(session, job_id=job_id)
        return True


def reclaim_and_notify_stuck_exports(session, factory) -> None:
    """Reprend les exports `running` trop vieux (worker tué) et notifie leur
    demandeur (REV-323 B : l'abandon était silencieux). Commit le statut AVANT
    de notifier — la notification reste best-effort (SP-39)."""
    reclaimed = [
        (job.tenant_id, job.item_id, job.user_id, job.page_id, job.error)
        for job_id in export_repo.reclaim_stuck_jobs(session)
        if (job := session.get(ExportJob, job_id)) is not None
    ]
    session.commit()
    for tenant_id, item_id, user_id, page_id, error in reclaimed:
        _notify(
            factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            page_id=page_id,
            resource_type=None,
            status="failure",
            error=error,
        )


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


USER_EXPORT_UNAVAILABLE = (
    "L'export n'est pas disponible pour le moment (configuration du serveur). "
    "Contactez l'administrateur."
)


def _published_core_url(shell_base_url: str) -> str | None:
    """URL du cœur que la page rendue appellera (VITE_CORE_URL d'env-config.js)."""
    try:
        with urllib.request.urlopen(f"{shell_base_url}/env-config.js", timeout=5) as r:
            match = re.search(r'VITE_CORE_URL:\s*"([^"]+)"', r.read().decode())
    except (OSError, ValueError):
        return None
    return match.group(1).rstrip("/") if match else None


def _core_answers(core_url: str) -> bool | str:
    """True si le cœur répond (même 404), sinon le texte de l'erreur réseau."""
    try:
        urllib.request.urlopen(f"{core_url}/health", timeout=5).close()
    except urllib.error.HTTPError as exc:
        exc.close()
        return True
    except (OSError, ValueError) as exc:
        return str(exc)
    return True


def core_unreachable_error(shell_base_url: str) -> str | None:
    """Message technique (journaux) si le cœur que la page rendue appellera n'est
    pas joignable depuis ce conteneur (j05b-006). None = joignable, ou impossible
    à vérifier (le rendu tranchera)."""
    core_url = _published_core_url(shell_base_url)
    if core_url is None:
        return None
    result = _core_answers(core_url)
    if result is True:
        return None
    return (
        f"le cœur ({core_url}), que la page d'export appelle (VITE_CORE_URL du shell), "
        f"n'est pas joignable depuis export-worker : {result}. Définir VITE_CORE_URL sur une "
        "URL atteignable à la fois du navigateur et d'export-worker, ou EXPORT_CORE_INTERNAL_URL "
        "(cf. .env.example)."
    )


def core_bridge_target(shell_base_url: str) -> tuple[str, str] | None:
    """AUD-133 : (url publique, url interne) du cœur quand le cœur publié (ex.
    http://localhost:8200, le défaut du compose) est injoignable depuis le
    Chromium du worker mais que `EXPORT_CORE_INTERNAL_URL` répond — la
    navigation du worker est alors relayée vers le cœur interne. None = pas
    besoin de pont, ou pont impossible."""
    internal = os.environ.get("EXPORT_CORE_INTERNAL_URL", "").rstrip("/")
    public = _published_core_url(shell_base_url)
    if not internal or public is None or public == internal:
        return None
    if _core_answers(public) is True or _core_answers(internal) is not True:
        return None
    return public, internal


_BRIDGE_ALLOW_HEADERS = "authorization,content-type,if-match,x-share-link-token"


def _core_bridge_handler(public: str, internal: str):
    """Handler `page.route` : relaie les appels de la page vers le cœur interne et
    pose les en-têtes CORS (le shell, `shell:8300`, appelle un autre hôte).
    Ne couvre QUE l'origine publique du cœur — aucun accès réseau élargi."""

    def handler(route) -> None:
        request = route.request
        cors = {
            "access-control-allow-origin": request.headers.get("origin", "*"),
            "access-control-allow-headers": _BRIDGE_ALLOW_HEADERS,
            "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "vary": "Origin",
        }
        if request.method == "OPTIONS":
            route.fulfill(status=204, headers=cors)
            return
        response = route.fetch(url=internal + request.url[len(public) :])
        route.fulfill(response=response, headers={**response.headers, **cors})

    return handler


def _launch_and_navigate(
    url: str,
    viewport: tuple[int, int] | None = None,
    core_bridge: tuple[str, str] | None = None,
) -> RenderPage:
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
    # ARC-16 : un seul budget de RENDER_TIMEOUT_MS pour navigation + prêt +
    # capture (le défaut Playwright s'applique ensuite à screenshot/pdf).
    deadline = time.monotonic() + RENDER_TIMEOUT_MS / 1000

    def remaining_ms() -> int:
        return max(1, int((deadline - time.monotonic()) * 1000))

    try:
        browser = playwright.chromium.launch(headless=True)
        page = (
            browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            if viewport
            else browser.new_page()
        )
        if core_bridge is not None:
            public, internal = core_bridge
            page.route(f"{public}/**", _core_bridge_handler(public, internal))
        page.goto(url, wait_until="load", timeout=remaining_ms())
        page.wait_for_selector(
            '[data-export-ready="true"]', timeout=remaining_ms(), state="attached"
        )
        page.set_default_timeout(remaining_ms())
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
    factory = session_factory()

    if not is_export_enabled():
        with request_scoped_session(factory) as session:
            export_repo.mark_error(session, job_id=job_id, error="export capability disabled")
        return

    # Toujours liés avant le premier bloc protégé : si get_job/mark_running
    # lève avant leur affectation réelle, le handler `except` plus bas doit
    # pouvoir les lire sans UnboundLocalError — même patron que
    # app.pipelines.jobs.run_pipeline_task/app.ingestion.tasks.run_ingestion_task
    # (GAP-56.1, SP-49 : ces deux appels étaient hors du bloc try ici, une
    # exception transitoire remontait alors non gérée — ni mark_error, ni
    # notification).
    item_id: str | None = None
    user_id: str | None = None
    export_format: str | None = None
    page_id = None

    try:
        with request_scoped_session(factory) as session:
            job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
            if job is None:
                logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
                return
            if not export_repo.mark_running(session, job_id=job_id):
                logger.warning("export job %s non prenable (déjà pris ou terminé)", job_id)
                return
            item_id, user_id, export_format = job.item_id, job.user_id, job.format
            page_id, ctx, scope = job.page_id, job.ctx, job.scope

        with request_scoped_session(factory) as session:
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
            target_url = f"{target_url}&ctx={quote(ctx, safe='')}"
        if scope == "atlas":
            target_url = f"{target_url}&atlas=1"
        elif scope and scope.startswith("entity:"):
            target_url = f"{target_url}&entityId={quote(scope[7:], safe='')}"

        shell_base_url = os.environ["SHELL_BASE_URL"]
        core_bridge = core_bridge_target(shell_base_url)
        if core_bridge is None and (reason := core_unreachable_error(shell_base_url)) is not None:
            # Détail d'exploitation dans les journaux ; l'utilisateur (barre,
            # cloche) ne reçoit qu'un message sans variable d'environnement.
            logger.error("export job %s : %s", job_id, reason)
            raise RuntimeError(USER_EXPORT_UNAVAILABLE)

        # ARC-16 : annulation demandée pendant l'attente en file / le démarrage.
        if _cancelled(factory, job_id):
            return

        browser_page = _launch_and_navigate(
            target_url, viewport=page_pixels(print_layout), core_bridge=core_bridge
        )
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

        # Dernier point d'annulation avant l'envoi (le rendu n'est pas interruptible).
        if _cancelled(factory, job_id):
            return

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
        with request_scoped_session(factory) as session:
            # SP-58 Tâche 2 (GAP-73) : `content` est déjà en mémoire (le
            # rendu vient d'être produit ci-dessus) — len() suffit, pas
            # besoin d'un head_object après upload (bucket non
            # tenant-préfixé, cf. spec §1.4/§3.1).
            done = export_repo.mark_done(
                session, job_id=job_id, result_key=result_key, byte_size=len(content)
            )
        if not done:  # REV-323 B : repris en erreur pendant l'envoi — objet orphelin
            logger.warning("export job %s terminé tardivement, objet supprimé", job_id)
            s3_client.delete_object(Bucket=bucket, Key=result_key)
            _cancelled(factory, job_id)  # annulé pendant l'envoi : statut final
            return
        _notify(
            factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            page_id=page_id,
            resource_type="map" if config.kind == "map" else "app",
            status="success",
        )
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("export job %s : erreur inattendue", job_id)
        with request_scoped_session(factory) as session:
            export_repo.mark_error(session, job_id=job_id, error=str(exc))
        _notify(
            factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            page_id=page_id,
            resource_type=None,
            status="failure",
            error=str(exc),
        )
