# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.terrain3d.models import Terrain3DJob


def create_job(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    source_key: str,
    filename: str,
    title: str,
) -> Terrain3DJob:
    job = Terrain3DJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_by=created_by,
        status="uploaded",
        source_key=source_key,
        filename=filename,
        title=title,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> Terrain3DJob | None:
    return session.scalar(
        select(Terrain3DJob).where(Terrain3DJob.id == job_id, Terrain3DJob.tenant_id == tenant_id)
    )


# mark_converting/mark_done/mark_error sont appelées depuis une route déjà
# tenant-scopée (get_job en amont) ou depuis le worker (qui a déjà validé le
# job via get_job(tenant_id=...) en tout début de tâche) — pas de
# re-filtrage par tenant ici, même discipline qu'app.tileset3d.repository.
def mark_converting(session: Session, *, job_id: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "converting"
    session.flush()


def mark_done(session: Session, *, job_id: str, item_id: str, converted_key: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.item_id = item_id
    job.converted_key = converted_key
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
