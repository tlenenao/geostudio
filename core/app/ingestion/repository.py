import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import IngestionJob


def create_job(
    session: Session, *, tenant_id: str, created_by: str, source_key: str,
    filename: str, collection_title: str,
    lat_field: str | None, lon_field: str | None,
) -> IngestionJob:
    job = IngestionJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, created_by=created_by,
        status="pending", source_key=source_key, filename=filename,
        collection_title=collection_title, lat_field=lat_field, lon_field=lon_field,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> IngestionJob | None:
    return session.scalar(
        select(IngestionJob).where(
            IngestionJob.id == job_id, IngestionJob.tenant_id == tenant_id
        )
    )


# mark_running/mark_done/mark_error sont appelées uniquement par le worker
# (app.ingestion.tasks), qui a déjà validé le job via get_job(tenant_id=...)
# au tout début de la tâche — pas de re-filtrage par tenant ici, job_id est
# un identifiant interne non devinable (uuid4) à ce stade, jamais fourni
# directement par une requête HTTP utilisateur.
def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "running"
    session.flush()


def mark_done(session: Session, *, job_id: str, collection_id: str, item_id: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.collection_id = collection_id
    job.item_id = item_id
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
