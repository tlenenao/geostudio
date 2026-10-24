# SPDX-License-Identifier: Apache-2.0
"""Job procrastinate de purge de tenant (SP-58 Tâche 10). Queue "etl" —
réutilisée par analogie avec reports/alerts/pipelines (même famille de
jobs longs, rares, non temps-réel) : une queue dédiée "compliance"
demanderait d'ajouter cette file à la liste `-q ...` du service `worker`
(docker-compose.yml) — un oubli à cet endroit laisserait le job déféré
mais jamais consommé par aucun worker (piège CLAUDE.md n°2, classe de
défaut déjà payée plusieurs fois dans ce dépôt), risque qu'évite le choix
de réutiliser une file déjà dans cette liste."""

import logging
import os

from app.collect.repository import purge_expired as purge_expired_client_ops
from app.compliance.models import PurgeReceipt
from app.compliance.orphans import sweep_orphan_job_objects
from app.compliance.purge import purge_tenant, retry_pending_s3_purges
from app.db import request_scoped_session
from app.history.service import purge_expired as purge_expired_history
from app.ingestion.storage import make_s3_client
from app.jobs import app
from app.jobs.common import session_factory as _session_factory
from app.notifications.repository import purge_expired_notifications


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _set_receipt_status(factory, purge_id: str, status: str, *, error: str | None = None) -> None:
    """Session dédiée, committée à part : survit à l'annulation de la transaction de purge."""
    with request_scoped_session(factory) as session:
        receipt = session.get(PurgeReceipt, purge_id)
        if receipt is not None:
            receipt.status = status
            receipt.error = error
            session.commit()


@app.task(queue="etl")
def purge_tenant_task(*, purge_id: str, tenant_id: str, requested_by_user_id: str) -> None:
    factory = _session_factory()
    _set_receipt_status(factory, purge_id, "running")
    try:
        s3 = s3_client_from_env()
        with request_scoped_session(factory) as session:
            purge_tenant(
                session,
                s3,
                tenant_id=tenant_id,
                requested_by_user_id=requested_by_user_id,
                receipt_id=purge_id,
            )
            session.commit()
    except Exception as exc:
        # REV-344 b : l'échec est consigné sur le reçu (GET /purges/{id} le rend visible,
        # une nouvelle demande redevient possible) au lieu de laisser un 202 éternel. La
        # transaction de purge est annulée : la base est intacte, S3 n'a pas été touché.
        logging.getLogger(__name__).exception("purge du tenant %s échouée", tenant_id)
        _set_receipt_status(factory, purge_id, "failed", error=f"{type(exc).__name__}: {exc}")


@app.periodic(cron="23 3 * * *")
@app.task(queue="etl", queueing_lock="sweep_orphan_job_objects_task")
def sweep_orphan_job_objects_task(timestamp: int) -> None:
    """Supprime les fichiers de résultat d'export/appexport dont le job a
    disparu (suppression d'item en CASCADE) et les objets des buckets
    uploads/attachments sans ligne vivante (REV-268). Quotidien, plafonné par passe.
    Pas de garde de flag : un bucket absent (capacité éteinte) est ignoré."""
    if not os.environ.get("S3_ENDPOINT_URL"):
        return
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        n = sweep_orphan_job_objects(session, s3_client_from_env())
    if n:
        logging.getLogger(__name__).info("%d objet(s) S3 orphelin(s) supprimé(s)", n)


@app.periodic(cron="41 3 * * *")
@app.task(queue="etl", queueing_lock="purge_entity_history_task")
def purge_entity_history_task(timestamp: int) -> None:
    """Rétention du journal d'entité (ARC-15, 365 j)."""
    with request_scoped_session(_session_factory()) as session:
        n = purge_expired_history(session)
        session.commit()
    if n:
        logging.getLogger(__name__).info("%d version(s) d'historique expirée(s) purgée(s)", n)


@app.periodic(cron="53 3 * * *")
@app.task(queue="etl", queueing_lock="purge_collect_client_ops_task")
def purge_collect_client_ops_task(timestamp: int) -> None:
    """Rétention de 30 j des clés d'idempotence de collecte (L8, AUD-004)."""
    with request_scoped_session(_session_factory()) as session:
        n = purge_expired_client_ops(session)
        session.commit()
    if n:
        logging.getLogger(__name__).info("%d clé(s) d'idempotence de collecte purgée(s)", n)


@app.periodic(cron="17 * * * *")
@app.task(queue="etl", queueing_lock="retry_pending_s3_purges_task")
def retry_pending_s3_purges_task(timestamp: int) -> None:
    """Reprend le nettoyage S3 d'une purge de tenant restée `done_with_s3_pending` (AUD-121)."""
    if not os.environ.get("S3_ENDPOINT_URL"):
        return
    with request_scoped_session(_session_factory()) as session:
        n = retry_pending_s3_purges(session, s3_client_from_env())
        session.commit()
    if n:
        logging.getLogger(__name__).info("%d purge(s) de tenant : nettoyage S3 soldé", n)


@app.periodic(cron="* * * * *")
@app.task(queue="etl", queueing_lock="seal_audit_chain_task")
def seal_audit_chain_task(timestamp: int) -> None:
    """Scelle (chaîne de hachage) les lignes d'audit non scellées, par tenant (AUD-092)."""
    from sqlalchemy import select

    from app.audit.chain import seal
    from app.audit.models import AuditLog

    with request_scoped_session(_session_factory()) as session:
        tenants = session.scalars(
            select(AuditLog.tenant_id).where(AuditLog.hash.is_(None)).distinct().limit(50)
        ).all()
        for tenant_id in tenants:
            seal(session, tenant_id)
        session.commit()


@app.periodic(cron="53 3 * * *")
@app.task(queue="etl", queueing_lock="audit_retention_task")
def audit_retention_task(timestamp: int) -> None:
    """Archive sur S3 puis supprime l'audit plus vieux que `CORE_AUDIT_RETENTION_DAYS` (AUD-092).
    Sans effet tant que la variable vaut 0 (défaut : conservation illimitée)."""
    from app.audit.retention import apply_retention, retention_days

    if retention_days() <= 0 or not os.environ.get("S3_ENDPOINT_URL"):
        return
    with request_scoped_session(_session_factory()) as session:
        n = apply_retention(session, s3_client_from_env())
        session.commit()
    if n:
        logging.getLogger(__name__).info("%d ligne(s) d'audit archivée(s) puis supprimée(s)", n)


@app.periodic(cron="57 3 * * *")
@app.task(queue="etl", queueing_lock="purge_notifications_task")
def purge_notifications_task(timestamp: int) -> None:
    """Rétention des notifications in-app : lues 90 j, non lues 365 j (REV-401)."""
    with request_scoped_session(_session_factory()) as session:
        n = purge_expired_notifications(session)
        session.commit()
    if n:
        logging.getLogger(__name__).info("%d notification(s) expirée(s) purgée(s)", n)
