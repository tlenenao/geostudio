# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-6a) : orchestre téléchargement S3 → pipeline
d'import (app.ingestion.importer.run_import) → mise à jour du statut du job.
Toute erreur (parsing ou inattendue) marque le job "error", jamais de job
bloqué en pending/running ("zombie", critère d'acceptation SP-6a).
L'instance procrastinate.App vit dans app.jobs (SP-7 Task 1) — partagée avec
les tâches d'embedding d'app.items/app.collections."""

import logging
import os

from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion import repository as ingestion_repo
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.ingestion.storage import download_object, make_s3_client
from app.jobs import app
from app.notifications import repository as notifications_repo

logger = logging.getLogger(__name__)


def _notify(
    session_factory,
    *,
    tenant_id: str,
    created_by: str,
    status: str,
    item_id: str | None,
    collection_title: str,
    error: str | None = None,
) -> None:
    """Écrit la notification in-app de fin de job — best-effort, jamais
    bloquant : son propre bloc try/except, séparé de celui qui commite
    mark_done/mark_error, pour qu'un échec ici ne fasse jamais rollback d'un
    changement de statut de job déjà réussi (cf. request_scoped_session)."""
    try:
        with request_scoped_session(session_factory) as session:
            notifications_repo.create_notification(
                session,
                tenant_id=tenant_id,
                recipient_user_id=created_by,
                kind="ingestion",
                status=status,
                item_id=item_id,
                item_resource_type="dataset" if item_id is not None else None,
                item_title=collection_title,
                error_message=error,
            )
    except Exception:
        logger.exception("ingestion job : échec de l'écriture de la notification")


def _make_s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _uploads_bucket() -> str:
    return os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")


@app.task(queue="ingestion")
def run_ingestion_task(job_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)

    # Toujours liés avant le premier bloc protégé : si get_job/mark_running
    # lève avant leur affectation réelle (ligne ~78), le handler générique
    # `except Exception` plus bas doit pouvoir les lire sans UnboundLocalError
    # (ce que la valeur None encode alors : « destinataire inconnu »).
    created_by: str | None = None
    collection_title: str | None = None

    try:
        with request_scoped_session(session_factory) as session:
            job = ingestion_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
            if job is None:
                logger.error("ingestion job %s introuvable (tenant %s)", job_id, tenant_id)
                return
            ingestion_repo.mark_running(session, job_id=job_id)
            filename, source_key, collection_title, lat_field, lon_field, layer_name, created_by = (
                job.filename,
                job.source_key,
                job.collection_title,
                job.lat_field,
                job.lon_field,
                job.layer_name,
                job.created_by,
            )

        s3 = _make_s3_client_from_env()
        content = download_object(s3, bucket=_uploads_bucket(), key=source_key)
        with request_scoped_session(session_factory) as session:
            result = run_import(
                session,
                tenant_id=tenant_id,
                created_by=created_by,
                filename=filename,
                content=content,
                collection_title=collection_title,
                lat_field=lat_field,
                lon_field=lon_field,
                layer_name=layer_name,
            )
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_done(
                session,
                job_id=job_id,
                collection_id=result.collection_id,
                item_id=result.item_id,
            )
        _notify(
            session_factory,
            tenant_id=tenant_id,
            created_by=created_by,
            status="success",
            item_id=result.item_id,
            collection_title=collection_title,
        )
    except IngestionParseError as exc:
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(session, job_id=job_id, error_message=str(exc))
        _notify(
            session_factory,
            tenant_id=tenant_id,
            created_by=created_by,
            status="failure",
            item_id=None,
            collection_title=collection_title,
            error=str(exc),
        )
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("ingestion job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(
                session, job_id=job_id, error_message=f"erreur interne : {exc}"
            )
        # created_by/collection_title restent None si l'échec a eu lieu avant
        # get_job/mark_running (cf. init en tête de fonction) : pas de
        # destinataire connu, donc pas de notification à écrire — le statut
        # du job est déjà marqué "error" ci-dessus, best-effort préservé.
        if created_by is not None:
            _notify(
                session_factory,
                tenant_id=tenant_id,
                created_by=created_by,
                status="failure",
                item_id=None,
                collection_title=collection_title or "",
                error=f"erreur interne : {exc}",
            )
        else:
            logger.info("ingestion job %s : notification ignorée (destinataire inconnu)", job_id)
