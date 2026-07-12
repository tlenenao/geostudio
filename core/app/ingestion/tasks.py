"""Tâche procrastinate (SP-6a) : orchestre téléchargement S3 → pipeline
d'import (app.ingestion.importer.run_import) → mise à jour du statut du job.
Toute erreur (parsing ou inattendue) marque le job "error", jamais de job
bloqué en pending/running ("zombie", critère d'acceptation SP-6a)."""
import logging
import os

import procrastinate

from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion import repository as ingestion_repo
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.ingestion.storage import download_object, make_s3_client

logger = logging.getLogger(__name__)


def _conninfo() -> str:
    # .get() avec repli, jamais os.environ[...] : ce module est importé
    # transitivement par app.main (via app.ingestion.routes, Task 4) dans
    # TOUTE la suite de tests, y compris les tests SQLite qui ne définissent
    # jamais DATABASE_URL — un KeyError ici casserait la collecte pytest
    # entière. Le repli n'est jamais utilisé pour de vrai (le worker/cœur
    # déployés reçoivent toujours DATABASE_URL via docker-compose).
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/geostudio_dev")
    return database_url.replace("postgresql+psycopg://", "postgresql://")


app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=_conninfo()))


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

    try:
        with request_scoped_session(session_factory) as session:
            job = ingestion_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
            if job is None:
                logger.error("ingestion job %s introuvable (tenant %s)", job_id, tenant_id)
                return
            ingestion_repo.mark_running(session, job_id=job_id)
            filename, source_key, collection_title, lat_field, lon_field, created_by = (
                job.filename, job.source_key, job.collection_title,
                job.lat_field, job.lon_field, job.created_by,
            )

        s3 = _make_s3_client_from_env()
        content = download_object(s3, bucket=_uploads_bucket(), key=source_key)
        with request_scoped_session(session_factory) as session:
            result = run_import(
                session, tenant_id=tenant_id, created_by=created_by, filename=filename,
                content=content, collection_title=collection_title,
                lat_field=lat_field, lon_field=lon_field,
            )
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_done(
                session, job_id=job_id,
                collection_id=result.collection_id, item_id=result.item_id,
            )
    except IngestionParseError as exc:
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(session, job_id=job_id, error_message=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("ingestion job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(
                session, job_id=job_id, error_message=f"erreur interne : {exc}"
            )
