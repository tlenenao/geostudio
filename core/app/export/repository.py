# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.export.models import ExportJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(session: Session, *, tenant_id: str, item_id: str, user_id: str, format: str) -> ExportJob:
    job = ExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        format=format, status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> ExportJob | None:
    return session.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = _now()
    session.flush()


def mark_done(session: Session, *, job_id: str, result_key: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.result_key = result_key
    job.finished_at = _now()
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error = error
    job.finished_at = _now()
    session.flush()
