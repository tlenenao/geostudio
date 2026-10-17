# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
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


def key_in_use(session: Session, *, tenant_id: str, key: str) -> bool:
    """La clé est déjà la source ou le COG converti d'un job : la ré-accepter
    ferait copier puis supprimer l'objet d'un autre (AUD-151)."""
    return (
        session.scalar(
            select(Terrain3DJob.id).where(
                Terrain3DJob.tenant_id == tenant_id,
                (Terrain3DJob.source_key == key) | (Terrain3DJob.converted_key == key),
            )
        )
        is not None
    )


# mark_converting/mark_done/mark_error sont appelées depuis une route déjà
# tenant-scopée (get_job en amont) ou depuis le worker (qui a déjà validé le
# job via get_job(tenant_id=...) en tout début de tâche) — pas de
# re-filtrage par tenant ici, même discipline qu'app.tileset3d.repository.
def mark_converting(session: Session, *, job_id: str) -> bool:
    """REV-295 : transition conditionnelle `uploaded -> converting` ; False si le
    job n'est plus prenable (déjà pris, terminé, inconnu)."""
    result = session.execute(
        update(Terrain3DJob)
        .where(Terrain3DJob.id == job_id, Terrain3DJob.status == "uploaded")
        .values(status="converting")
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


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


# Seuil de reprise (minutes), > timeout de conversion (15 min) ; pas de variable d'env (YAGNI).
RECLAIM_MINUTES = 60


def reclaim_stuck_jobs(
    session: Session, *, older_than_minutes: int | None = None
) -> list[Terrain3DJob]:
    """REV-345 : jobs restés `uploaded`/`converting` au-delà du seuil (worker tué,
    `.defer()` perdu) -> `error`. Conditionnel sur le statut lu : un `done` committé
    entre-temps n'est pas écrasé. Même patron que app.appexport.repository."""
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes or RECLAIM_MINUTES)
    rows = (
        session.execute(
            select(Terrain3DJob).where(
                Terrain3DJob.status.in_(("uploaded", "converting")),
                Terrain3DJob.updated_at < threshold,
            )
        )
        .scalars()
        .all()
    )
    reclaimed: list[Terrain3DJob] = []
    for job in rows:
        claimed = session.execute(
            update(Terrain3DJob)
            .where(Terrain3DJob.id == job.id, Terrain3DJob.status == job.status)
            .values(
                status="error", error_message="conversion abandonnée (worker arrêté ou file perdue)"
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job)
    if reclaimed:
        session.flush()
    return reclaimed
