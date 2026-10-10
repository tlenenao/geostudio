# SPDX-License-Identifier: Apache-2.0
import os
import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.dataexport.models import CollectionExportJob, _now

_TERMINAL = ("done", "failed")


def create_job(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    requested_by: str,
    fmt: str,
    masked: bool,
    query: dict | None = None,
) -> CollectionExportJob:
    job = CollectionExportJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        collection_id=collection_id,
        requested_by=requested_by,
        format=fmt,
        status="pending",
        masked=masked,
        query=query,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: str, tenant_id: str) -> CollectionExportJob | None:
    return session.execute(
        select(CollectionExportJob).where(
            CollectionExportJob.id == job_id, CollectionExportJob.tenant_id == tenant_id
        )
    ).scalar_one_or_none()


def mark_running(session: Session, job_id: str) -> bool:
    """REV-295 : transition conditionnelle `pending -> running` ; False si le job
    n'est plus prenable (déjà pris, terminé, inconnu)."""
    result = session.execute(
        update(CollectionExportJob)
        .where(CollectionExportJob.id == job_id, CollectionExportJob.status == "pending")
        .values(status="running", started_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(session: Session, job_id: str, *, result_key: str, filename: str) -> bool:
    """False si le job est deja terminal (ex. repris en `failed` pendant l'envoi)."""
    result = session.execute(
        update(CollectionExportJob)
        .where(CollectionExportJob.id == job_id, CollectionExportJob.status.notin_(_TERMINAL))
        .values(status="done", result_key=result_key, filename=filename, finished_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_failed(session: Session, job_id: str, error: str) -> None:
    session.execute(
        update(CollectionExportJob)
        .where(CollectionExportJob.id == job_id, CollectionExportJob.status.notin_(_TERMINAL))
        .values(status="failed", error=error, finished_at=_now())
    )
    session.flush()


BATCH = 100
PENDING_RETRY_MINUTES = 5
RUNNING_RECLAIM_MINUTES = 60  # defaut ; CORE_EXPORT_RUNNING_TIMEOUT_MINUTES le surcharge


def running_reclaim_minutes() -> int:
    """Duree max d'un export `running` avant reprise en `failed` (worker tue)."""
    return int(os.environ.get("CORE_EXPORT_RUNNING_TIMEOUT_MINUTES") or RUNNING_RECLAIM_MINUTES)


def stale_pending_ids(session: Session, *, older_than_minutes: int = PENDING_RETRY_MINUTES):
    """Jobs `pending` dont le defer a échoué ou s'est perdu (commit puis defer)."""
    threshold = _now() - timedelta(minutes=older_than_minutes)
    rows = session.execute(
        select(CollectionExportJob.id, CollectionExportJob.tenant_id)
        .where(CollectionExportJob.status == "pending", CollectionExportJob.created_at < threshold)
        .limit(BATCH)
    ).all()
    return [(r.id, r.tenant_id) for r in rows]


def reclaim_stuck_running(session: Session, *, older_than_minutes: int | None = None) -> list[str]:
    """`running` sans fin depuis trop longtemps (worker tué) -> `failed`.
    Compare-and-swap sur started_at : un job terminé ou repris entre-temps
    n'est pas écrasé."""
    threshold = _now() - timedelta(minutes=older_than_minutes or running_reclaim_minutes())
    rows = session.execute(
        select(CollectionExportJob.id, CollectionExportJob.started_at)
        .where(CollectionExportJob.status == "running", CollectionExportJob.started_at < threshold)
        .limit(BATCH)
    ).all()
    reclaimed: list[str] = []
    for job_id, started_at in rows:
        claimed = session.execute(
            update(CollectionExportJob)
            .where(
                CollectionExportJob.id == job_id,
                CollectionExportJob.status == "running",
                CollectionExportJob.started_at == started_at,
            )
            .values(
                status="failed",
                error="export timed out (worker crashed or hung)",
                finished_at=_now(),
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job_id)
    session.flush()
    return reclaimed


def expired_terminal_jobs(session: Session) -> list[tuple[str, str | None]]:
    """(id, result_key) des jobs terminés dont le TTL est dépassé ; jamais un
    `pending`/`running` (un job récent encore actif ne doit pas être purgé)."""
    rows = session.execute(
        select(CollectionExportJob.id, CollectionExportJob.result_key)
        .where(CollectionExportJob.status.in_(_TERMINAL), CollectionExportJob.expires_at < _now())
        .limit(BATCH)
    ).all()
    return [(r.id, r.result_key) for r in rows]


def delete_job(session: Session, job_id: str) -> None:
    session.execute(
        delete(CollectionExportJob).where(
            CollectionExportJob.id == job_id, CollectionExportJob.status.in_(_TERMINAL)
        )
    )
    session.flush()
