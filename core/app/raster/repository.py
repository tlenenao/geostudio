# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.raster.models import RasterAsset, RasterJob

# Seuil de reprise (minutes) des jobs zombies, > timeout de conversion (15 min).
RECLAIM_MINUTES = 60


def create_job(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    source_key: str,
    filename: str,
    title: str,
    limit_collection_id: str | None = None,
) -> RasterJob:
    job = RasterJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_by=created_by,
        status="uploaded",
        source_key=source_key,
        filename=filename,
        title=title,
        limit_collection_id=limit_collection_id,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def key_in_use(session: Session, *, tenant_id: str, key: str) -> bool:
    """La clé est déjà la source/le COG d'un job, ou la source d'un raster."""
    return (
        session.scalar(
            select(RasterJob.id).where(
                RasterJob.tenant_id == tenant_id,
                (RasterJob.source_key == key) | (RasterJob.converted_key == key),
            )
        )
        is not None
        or session.scalar(
            select(RasterAsset.item_id).where(
                RasterAsset.tenant_id == tenant_id, RasterAsset.source_key == key
            )
        )
        is not None
    )


def get_job(session: Session, *, tenant_id: str, job_id: str) -> RasterJob | None:
    return session.scalar(
        select(RasterJob).where(RasterJob.id == job_id, RasterJob.tenant_id == tenant_id)
    )


def mark_converting(session: Session, *, job_id: str) -> bool:
    """Transition conditionnelle `uploaded -> converting` (un seul worker gagne)."""
    result = session.execute(
        update(RasterJob)
        .where(RasterJob.id == job_id, RasterJob.status == "uploaded")
        .values(status="converting")
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(session: Session, *, job_id: str, item_id: str, converted_key: str) -> None:
    job = session.get(RasterJob, job_id)
    if job is not None:
        job.status, job.item_id, job.converted_key = "done", item_id, converted_key
        session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(RasterJob, job_id)
    if job is not None:
        job.status, job.error_message = "error", error_message
        session.flush()


def reclaim_stuck_jobs(
    session: Session, *, older_than_minutes: int | None = None
) -> list[RasterJob]:
    """Jobs restés `uploaded`/`converting` au-delà du seuil (worker tué, `.defer()` perdu)
    -> `error`. Conditionnel sur le statut lu : un `done` committé entre-temps survit.
    Jumelle de garde du patron « commit puis defer » (piège n°14)."""
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes or RECLAIM_MINUTES)
    rows = (
        session.execute(
            select(RasterJob).where(
                RasterJob.status.in_(("uploaded", "converting")),
                RasterJob.updated_at < threshold,
            )
        )
        .scalars()
        .all()
    )
    reclaimed: list[RasterJob] = []
    for job in rows:
        claimed = session.execute(
            update(RasterJob)
            .where(RasterJob.id == job.id, RasterJob.status == job.status)
            .values(
                status="error", error_message="ingestion abandonnée (worker arrêté ou file perdue)"
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job)
    if reclaimed:
        session.flush()
    return reclaimed


def get_asset(session: Session, *, tenant_id: str, item_id: str) -> RasterAsset | None:
    return session.scalar(
        select(RasterAsset).where(
            RasterAsset.item_id == item_id, RasterAsset.tenant_id == tenant_id
        )
    )
