# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tileset3d.models import Tileset3DJob


def create_job(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    source_key: str,
    upload_id: str,
    filename: str,
    title: str,
) -> Tileset3DJob:
    job = Tileset3DJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_by=created_by,
        status="pending",
        source_key=source_key,
        upload_id=upload_id,
        filename=filename,
        title=title,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> Tileset3DJob | None:
    return session.scalar(
        select(Tileset3DJob).where(Tileset3DJob.id == job_id, Tileset3DJob.tenant_id == tenant_id)
    )


# mark_finalizing/mark_done/mark_error sont appelées uniquement depuis une
# route déjà tenant-scopée (get_job en amont) ou depuis le worker (qui a
# déjà validé le job via get_job(tenant_id=...) en tout début de tâche) —
# pas de re-filtrage par tenant ici, même discipline qu'app.ingestion.repository.
def mark_finalizing(session: Session, *, job_id: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "finalizing"
    session.flush()


def mark_done(session: Session, *, job_id: str, item_id: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.item_id = item_id
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
