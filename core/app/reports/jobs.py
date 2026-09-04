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
from app.auth.dependency import is_export_enabled, is_read_only_mode
from app.configs import repository as configs_repo
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task, s3_client_from_env
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.items.models import Item
from app.jobs import app
from app.notifications import repository as notifications_repo
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


def _audit_trigger_failure(session, *, tenant_id: str, item_id: str, error: str) -> None:
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=None,
        actor_kind="agent",
        action="report.run",
        object_type="item",
        object_id=item_id,
        payload={"success": False, "error": error},
    )


def _notify(
    session_factory,
    *,
    tenant_id: str,
    item_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Écrit la notification in-app de rapport — best-effort, jamais bloquant,
    dans SA PROPRE session isolée du sweep (revue finale SP-39, I1) : ce
    helper n'est appelé qu'APRÈS que l'appelant (_record_trigger_failure,
    _notify_pending_reports) a déjà committé son propre run+audit sur SA
    propre session — jamais en partageant sa transaction. Avant ce correctif,
    la même session servait aux deux : un DBAPIError réel dans
    create_notification (son session.flush() interne) empoisonnait la
    transaction, et le session.commit()/mark_notified qui suivait levait à
    son tour — perdant les lignes run+audit déjà en attente ET, pour
    _record_trigger_failure, laissant l'exception s'échapper dans la boucle
    multi-tenant de _trigger_due_reports (elle n'attrape que ReportTriggerError
    et Exception autour de l'appel à _record_trigger_failure lui-même, pas
    une exception levée PAR lui) — abortant le balayage pour tous les tenants
    restants de ce tick. Isoler l'écriture dans sa propre
    request_scoped_session (même patron que app.pipelines.jobs._notify /
    app.export.jobs._notify / app.appexport.jobs._notify /
    app.ingestion.tasks._notify) rend les deux impossibles : son
    commit/rollback est local à cette session, jamais à celle de l'appelant,
    qui a déjà committé avant cet appel."""
    try:
        with request_scoped_session(session_factory) as session:
            owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)
            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
            notifications_repo.create_notification(
                session,
                tenant_id=tenant_id,
                recipient_user_id=owner.id,
                kind="report",
                status=status,
                item_id=item_id,
                item_resource_type="report",
                item_title=item.title if item is not None else item_id,
                error_message=error,
            )
    except Exception:
        # Best-effort (Global Constraints) : couvre à la fois
        # ReportTriggerError (propriétaire introuvable — item supprimé entre
        # l'échec initial et ce point, rien à notifier, le run+audit déjà
        # écrits par l'appelant suffisent) ET toute erreur inattendue.
        logger.exception(
            "rapport %s : échec de l'écriture de la notification",
            item_id,
        )


def _record_trigger_failure(
    session, *, tenant_id: str, item_id: str, error: str, session_factory
) -> None:
    """Chemin d'échec unique du déclenchement (ReportTriggerError attendue ou
    erreur inattendue) : on annule d'abord les écritures partielles de cette
    itération (un export_jobs créé juste avant l'échec, par exemple), puis on
    audite l'échec et on committe — le balayage passe au rapport suivant.

    Crée AUSSI une ligne report_runs sans export_job_id (revue finale SP-17b,
    I2) : list_due_reports dérive « ce rapport est-il dû ? » de
    get_latest_run, donc un rapport sans aucun run était rejugé dû à chaque
    balayage de 5 minutes — un rapport définitivement cassé produisait des
    centaines de lignes d'audit par jour au lieu d'une par cycle cron. Même
    raisonnement qu'AlertRule, qui persiste toujours une évaluation
    (state="error") pour que la cadence soit respectée en échec comme en
    succès. Le run est marqué notifié immédiatement : aucun rendu n'a été mis
    en file, il n'y a rien à notifier — l'audit report.run porte l'échec.

    La notification in-app est écrite APRÈS ce commit, via _notify (session
    isolée, revue finale SP-39/I1) — jamais sur `session` : voir le docstring
    de _notify pour la raison exacte (transaction empoisonnée + abort du
    sweep multi-tenant, les deux modes de défaillance que ça évite)."""
    session.rollback()
    run = reports_repo.create_run(
        session,
        tenant_id=tenant_id,
        report_item_id=item_id,
        export_job_id=None,
    )
    reports_repo.mark_notified(session, run_id=run.id)
    _audit_trigger_failure(session, tenant_id=tenant_id, item_id=item_id, error=error)
    session.commit()
    _notify(session_factory, tenant_id=tenant_id, item_id=item_id, status="failure", error=error)


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

                # Fail-fast (revue finale SP-17b, I3) : la création est déjà
                # refusée en 403 quand la capacité export est coupée, mais un
                # rapport créé AVANT que l'admin ne la coupe reste en base.
                # Sans cette garde, son rendu serait déféré sur une file
                # `export` que personne ne dépile et resterait "pending" à
                # jamais (reclaim_stuck_jobs ne récupère que les "running").
                if not is_export_enabled():
                    raise ReportTriggerError("export capability disabled on this instance")

                owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)

                bookmark_facts = items_repo.get_access_facts(
                    session,
                    tenant_id=tenant_id,
                    item_id=payload.bookmarkItemId,
                )
                if bookmark_facts is None or not can(
                    session, user_id=owner.id, action="read", item=bookmark_facts
                ):
                    raise ReportTriggerError("bookmark not readable by report owner")

                bookmark_config = configs_repo.get_config_by_item(session, payload.bookmarkItemId)
                if bookmark_config is None or bookmark_config.kind != "bookmark":
                    raise ReportTriggerError("bookmark config not found")
                bookmark = bookmark_config.config.bookmark
                assert bookmark is not None

                app_facts = items_repo.get_access_facts(
                    session, tenant_id=tenant_id, item_id=bookmark.appId
                )
                if app_facts is None or not can(
                    session, user_id=owner.id, action="read", item=app_facts
                ):
                    raise ReportTriggerError("target app not readable by report owner")

                ctx = encode_analytics_context(bookmark)
                job = export_repo.create_job(
                    session,
                    tenant_id=tenant_id,
                    item_id=bookmark.appId,
                    user_id=owner.id,
                    format="pdf",
                    page_id=bookmark.pageId,
                    ctx=ctx,
                )
                run = reports_repo.create_run(
                    session,
                    tenant_id=tenant_id,
                    report_item_id=item_id,
                    export_job_id=job.id,
                )
                write_audit(
                    session,
                    tenant_id=tenant_id,
                    actor_id=owner.id,
                    actor_kind="agent",
                    action="report.run",
                    object_type="report_run",
                    object_id=run.id,
                    payload={"reportItemId": item_id, "exportJobId": job.id, "success": True},
                )
                session.commit()
                try:
                    render_export_task.defer(job_id=job.id, tenant_id=tenant_id)
                except Exception as exc:
                    # Le run et son export_jobs sont déjà committés (patron
                    # commit-avant-defer) : si la mise en file échoue, plus
                    # personne ne dépilera jamais ce job, il resterait
                    # "pending" indéfiniment et reclaim_stuck_jobs ne
                    # récupère que les "running". On le clôt en erreur pour
                    # que l'étape de notification le voie au tick suivant et
                    # notifie l'échec, comme pour n'importe quel rendu raté.
                    logger.exception("rapport %s : mise en file du rendu impossible", item_id)
                    export_repo.mark_error(
                        session,
                        job_id=job.id,
                        error=f"mise en file impossible : {exc}",
                    )
                    _audit_trigger_failure(
                        session,
                        tenant_id=tenant_id,
                        item_id=item_id,
                        error=f"mise en file impossible : {exc}",
                    )
                    session.commit()
            except ReportTriggerError as exc:
                logger.warning("report %s trigger failed: %s", item_id, exc)
                _record_trigger_failure(
                    session,
                    tenant_id=tenant_id,
                    item_id=item_id,
                    error=str(exc),
                    session_factory=session_factory,
                )
            except Exception as exc:
                # Jumeau du filet large d'app.alerts.jobs : tout ce qui est
                # dans le `try` et n'est PAS une ReportTriggerError
                # (render_export_task.defer contre un vrai Postgres, l'assert
                # de _owner_user, write_audit, les session.commit()) sortait
                # auparavant de _trigger_due_reports : un incident transitoire
                # sur le rapport n°1 abandonnait les rapports n°2..N de tous
                # les tenants pour ce tick, et sautait le
                # export_repo.reclaim_stuck_jobs final.
                logger.exception("rapport %s : erreur inattendue au déclenchement", item_id)
                _record_trigger_failure(
                    session,
                    tenant_id=tenant_id,
                    item_id=item_id,
                    error=f"erreur interne : {exc}",
                    session_factory=session_factory,
                )
        export_repo.reclaim_stuck_jobs(session)
        session.commit()


# 7 jours. TTL volontairement plus long que le défaut d'1 h de
# generate_presigned_get_url (revue finale SP-17b, I4) : ce lien part dans un
# e-mail ou un webhook déclenché par un cron nocturne ou de week-end, il est
# lu des heures voire des jours plus tard. Le défaut court reste le bon
# ailleurs — GET /reports/{id}/runs re-signe à chaque sondage, il n'y a rien
# à prolonger là-bas.
_NOTIFICATION_URL_TTL_SECONDS = 604_800


def _presigned_url_for_job(job) -> str | None:
    if job.status != "done" or not job.result_key:
        return None
    bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    return generate_presigned_get_url(
        s3_client_from_env(),
        bucket=bucket,
        key=job.result_key,
        expires_in=_NOTIFICATION_URL_TTL_SECONDS,
    )


def _notify_pending_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        for run in reports_repo.list_unnotified_runs(session):
            if run.export_job_id is None:
                # Run de déclenchement échoué (cf. _record_trigger_failure,
                # qui le marque déjà notifié) : aucun rendu n'a jamais été mis
                # en file, il n'y a rien à notifier. Filet de sécurité au cas
                # où le marquage n'aurait pas été committé.
                reports_repo.mark_notified(session, run_id=run.id)
                session.commit()
                continue
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

                item = items_repo.get_item(
                    session, tenant_id=run.tenant_id, item_id=run.report_item_id
                )
                title = item.title if item is not None else run.report_item_id
                result_url = _presigned_url_for_job(job)
                # Session isolée du sweep (revue finale SP-39, I1) : voir le
                # docstring de _notify — ne jamais écrire cette notification
                # sur `session`, qui porte aussi le mark_notified/commit du
                # `finally` ci-dessous.
                _notify(
                    session_factory,
                    tenant_id=run.tenant_id,
                    item_id=run.report_item_id,
                    status="success" if job.status == "done" else "failure",
                    error=job.error,
                )
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
                                payload={
                                    "reportItemId": run.report_item_id,
                                    "status": job.status,
                                    "resultUrl": result_url,
                                    "error": job.error,
                                },
                            )
                        elif isinstance(channel, AlertChannelEmail):
                            send_email(
                                session,
                                tenant_id=run.tenant_id,
                                channel=channel,
                                subject=f"[GeoStudio] Rapport : {title}",
                                body=message,
                            )
                        success = True
                    except NotifyError as exc:
                        error_detail = str(exc)
                        logger.warning("report notification failed for run %s: %s", run.id, exc)
                    write_audit(
                        session,
                        tenant_id=run.tenant_id,
                        actor_id=None,
                        actor_kind="agent",
                        action="report.notify",
                        object_type="item",
                        object_id=run.report_item_id,
                        payload={
                            "channel": channel.kind,
                            "success": success,
                            "error": error_detail,
                        },
                    )
            except Exception as exc:
                logger.exception("notification du run de rapport %s : erreur inattendue", run.id)
                try:
                    write_audit(
                        session,
                        tenant_id=run.tenant_id,
                        actor_id=None,
                        actor_kind="agent",
                        action="report.notify",
                        object_type="item",
                        object_id=run.report_item_id,
                        payload={
                            "channel": None,
                            "success": False,
                            "error": f"erreur interne : {exc}",
                        },
                    )
                except (
                    Exception
                ):  # session déjà cassée : l'audit ne doit pas empêcher mark_notified
                    logger.exception(
                        "audit d'échec de notification impossible pour le run %s", run.id
                    )
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
