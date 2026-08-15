# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Même discipline de reclaim-par-âge que app.export.repository (anchored on
# started_at, jamais created_at — un job resté "pending" en file avant de
# démarrer ne doit pas être réclamé dès qu'il passe "running").
_RUNNING_RECLAIM_MINUTES = 60


def create_job(
    session: Session, *, tenant_id: str, item_id: str, user_id: str, mode: str,
) -> AppExportJob:
    job = AppExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        mode=mode, status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> AppExportJob | None:
    return session.execute(
        select(AppExportJob).where(AppExportJob.id == job_id, AppExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = _now()
    session.flush()


def mark_done(session: Session, *, job_id: str, result_key: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.result_key = result_key
    job.finished_at = _now()
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error = error
    job.finished_at = _now()
    session.flush()


def reclaim_stuck_jobs(session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES) -> list[str]:
    threshold = _now() - timedelta(minutes=older_than_minutes)
    rows = session.execute(
        select(AppExportJob).where(AppExportJob.status == "running")
    ).scalars().all()
    reclaimed: list[str] = []
    for job in rows:
        started_at = job.started_at
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at >= threshold:
            continue
        job.status = "error"
        job.error = "app export timed out (worker crashed or hung)"
        job.finished_at = _now()
        reclaimed.append(job.id)
    if reclaimed:
        session.flush()
    return reclaimed
