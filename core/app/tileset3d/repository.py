# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
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
def mark_finalizing(session: Session, *, job_id: str) -> bool:
    """REV-295 : transition conditionnelle `pending -> finalizing` ; False si le
    job n'est plus prenable (déjà pris, terminé, inconnu)."""
    result = session.execute(
        update(Tileset3DJob)
        .where(Tileset3DJob.id == job_id, Tileset3DJob.status == "pending")
        .values(status="finalizing")
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


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


# Seuil de reprise (minutes), > timeout de conversion (15 min) ; pas de variable d'env (YAGNI).
RECLAIM_MINUTES = 60


def mark_enqueue_failed(session: Session, *, job_id: str) -> bool:
    """AUD-025 : mise en file définitivement impossible -> `pending -> error` tout de suite
    (UPDATE conditionnel : un job déjà pris par un worker n'est jamais écrasé)."""
    result = session.execute(
        update(Tileset3DJob)
        .where(Tileset3DJob.id == job_id, Tileset3DJob.status == "pending")
        .values(status="error", error_message="mise en file impossible : file de jobs indisponible")
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def reclaim_stuck_jobs(
    session: Session, *, older_than_minutes: int | None = None
) -> list[Tileset3DJob]:
    """REV-345 : jobs restés `pending`/`finalizing` au-delà du seuil (worker tué,
    `.defer()` perdu) -> `error`. Conditionnel sur le statut lu : un `done` committé
    entre-temps n'est pas écrasé. Même patron que app.appexport.repository."""
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes or RECLAIM_MINUTES)
    rows = (
        session.execute(
            select(Tileset3DJob).where(
                Tileset3DJob.status.in_(("pending", "finalizing")),
                Tileset3DJob.updated_at < threshold,
            )
        )
        .scalars()
        .all()
    )
    reclaimed: list[Tileset3DJob] = []
    for job in rows:
        claimed = session.execute(
            update(Tileset3DJob)
            .where(Tileset3DJob.id == job.id, Tileset3DJob.status == job.status)
            .values(
                status="error",
                error_message="finalisation abandonnée (worker arrêté ou file perdue)",
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job)
    if reclaimed:
        session.flush()
    return reclaimed
