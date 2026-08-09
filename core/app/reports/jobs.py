# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate pour ReportSchedule (design SP-17b §2) — reproduit
exactement app.alerts.jobs/app.pipelines.jobs : un sweep périodique, deux
étapes par tick (déclencher les planifications dues, puis notifier les runs
dont le rendu est terminé), commit-avant-defer à l'intérieur de la boucle
par élément pour la même raison que run_pipeline_sweep_task. La permission
est revérifiée au moment du déclenchement contre le PROPRIÉTAIRE du rapport
(pas le créateur de la planification, si jamais ils divergent — reproduit
app.alerts.jobs._owner_user) : un rapport dont le propriétaire a perdu
l'accès en lecture à son bookmark/app échoue proprement (audité, pas de
rendu) plutôt que de faire planter le sweep ou de rendre silencieusement
avec des droits élevés."""
import logging
import os

from sqlalchemy import select

from app.alerts.notify import NotifyError, send_email, send_webhook
from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs import repository as configs_repo
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task, s3_client_from_env
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.items.models import Item
from app.jobs import app
from app.reports import repository as reports_repo
from app.reports.ctx import encode_analytics_context
from app.sharing.authorization import can
from app.users.models import User

logger = logging.getLogger(__name__)


class ReportTriggerError(Exception):
    """Tout ce qui empêche un rapport dû d'être rendu — toujours capturé,
    toujours transformé en entrée audit_log, jamais un plantage du sweep."""


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _owner_user(session, *, tenant_id: str, item_id: str) -> User:
    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise ReportTriggerError(f"report schedule '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _trigger_due_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        due = reports_repo.list_due_reports(session)
        for item_id, tenant_id in due:
            try:
                config = configs_repo.get_config_by_item(session, item_id)
                if config is None or config.kind != "report":
                    continue
                payload = config.config.report
                assert payload is not None

                owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)

                bookmark_facts = items_repo.get_access_facts(
                    session, tenant_id=tenant_id, item_id=payload.bookmarkItemId,
                )
                if bookmark_facts is None or not can(session, user_id=owner.id, action="read", item=bookmark_facts):
                    raise ReportTriggerError("bookmark not readable by report owner")

                bookmark_config = configs_repo.get_config_by_item(session, payload.bookmarkItemId)
                if bookmark_config is None or bookmark_config.kind != "bookmark":
                    raise ReportTriggerError("bookmark config not found")
                bookmark = bookmark_config.config.bookmark
                assert bookmark is not None

                app_facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=bookmark.appId)
                if app_facts is None or not can(session, user_id=owner.id, action="read", item=app_facts):
                    raise ReportTriggerError("target app not readable by report owner")

                ctx = encode_analytics_context(bookmark)
                job = export_repo.create_job(
                    session, tenant_id=tenant_id, item_id=bookmark.appId, user_id=owner.id, format="pdf",
                    page_id=bookmark.pageId, ctx=ctx,
                )
                run = reports_repo.create_run(
                    session, tenant_id=tenant_id, report_item_id=item_id, export_job_id=job.id,
                )
                write_audit(
                    session, tenant_id=tenant_id, actor_id=owner.id, actor_kind="agent",
                    action="report.run", object_type="report_run", object_id=run.id,
                    payload={"reportItemId": item_id, "exportJobId": job.id, "success": True},
                )
                session.commit()
                render_export_task.defer(job_id=job.id, tenant_id=tenant_id)
            except ReportTriggerError as exc:
                logger.warning("report %s trigger failed: %s", item_id, exc)
                write_audit(
                    session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                    action="report.run", object_type="item", object_id=item_id,
                    payload={"success": False, "error": str(exc)},
                )
                session.commit()
        export_repo.reclaim_stuck_jobs(session)
        session.commit()


def _presigned_url_for_job(job) -> str | None:
    if job.status != "done" or not job.result_key:
        return None
    bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    return generate_presigned_get_url(s3_client_from_env(), bucket=bucket, key=job.result_key)


def _notify_pending_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        for run in reports_repo.list_unnotified_runs(session):
            job = export_repo.get_job(session, tenant_id=run.tenant_id, job_id=run.export_job_id)
            if job is None or job.status not in ("done", "error"):
                continue  # rendu encore en cours — on repassera au tick suivant

            # Filet large, jumeau de celui d'app.alerts.jobs.evaluate_alert_task :
            # tout ce qui suit peut lever autre chose qu'une NotifyError
            # (KeyError sur S3_ENDPOINT_URL absent et erreurs botocore dans
            # _presigned_url_for_job, KeyError/RuntimeError du chargement de
            # la clé maître ou InvalidTag AES-GCM sur une ligne de secret
            # corrompue dans send_email...). Sans ce filet, l'exception
            # s'échappait de _notify_pending_reports AVANT mark_notified :
            # list_unnotified_runs étant cross-tenant et non ordonnée, un seul
            # run cassé bloquait définitivement la notification de tous les
            # rapports de tous les tenants, à chaque balayage — exactement la
            # contrainte « une notification est tentée une fois par run,
            # jamais rejouée, même en échec » que ce filet garantit désormais
            # aussi pour le chemin d'erreur inattendue.
            try:
                report_config = configs_repo.get_config_by_item(session, run.report_item_id)
                if report_config is None or report_config.kind != "report":
                    # Item du rapport supprimé après déclenchement — plus rien
                    # contre quoi notifier ; on clôture le run (finally
                    # ci-dessous) pour que le sweep ne boucle pas dessus
                    # indéfiniment.
                    continue
                payload = report_config.config.report
                assert payload is not None

                item = items_repo.get_item(session, tenant_id=run.tenant_id, item_id=run.report_item_id)
                title = item.title if item is not None else run.report_item_id
                result_url = _presigned_url_for_job(job)
                message = (
                    f"Rapport « {title} » : {job.status}."
                    + (f" Lien : {result_url}" if result_url else "")
                    + (f" Erreur : {job.error}" if job.error else "")
                )

                for channel in payload.channels:
                    success = False
                    error_detail = None
                    try:
                        if isinstance(channel, AlertChannelWebhook):
                            send_webhook(
                                channel,
                                payload={"reportItemId": run.report_item_id, "status": job.status,
                                          "resultUrl": result_url, "error": job.error},
                            )
                        elif isinstance(channel, AlertChannelEmail):
                            send_email(
                                session, tenant_id=run.tenant_id, channel=channel,
                                subject=f"[GeoStudio] Rapport : {title}", body=message,
                            )
                        success = True
                    except NotifyError as exc:
                        error_detail = str(exc)
                        logger.warning("report notification failed for run %s: %s", run.id, exc)
                    write_audit(
                        session, tenant_id=run.tenant_id, actor_id=None, actor_kind="agent",
                        action="report.notify", object_type="item", object_id=run.report_item_id,
                        payload={"channel": channel.kind, "success": success, "error": error_detail},
                    )
            except Exception as exc:
                logger.exception("notification du run de rapport %s : erreur inattendue", run.id)
                try:
                    write_audit(
                        session, tenant_id=run.tenant_id, actor_id=None, actor_kind="agent",
                        action="report.notify", object_type="item", object_id=run.report_item_id,
                        payload={"channel": None, "success": False, "error": f"erreur interne : {exc}"},
                    )
                except Exception:  # session déjà cassée : l'audit ne doit pas empêcher mark_notified
                    logger.exception("audit d'échec de notification impossible pour le run %s", run.id)
            finally:
                # Posé après la tentative, quel que soit le résultat par canal
                # ET quelle que soit l'erreur inattendue ci-dessus — une
                # notification n'est jamais rejouée au tick suivant (design
                # SP-17b §2, cf. le risque documenté "webhook cassé de façon
                # permanente ne doit pas devenir un déni de service").
                reports_repo.mark_notified(session, run_id=run.id)
                session.commit()


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def sweep_report_schedules_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de rapports planifiés ignoré")
        return
    session_factory = _session_factory()
    _trigger_due_reports(session_factory)
    _notify_pending_reports(session_factory)
