# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import IngestionJob

# Même seuil que app.export.repository/app.appexport.repository
# (_RUNNING_RECLAIM_MINUTES) et app.pipelines.repository/app.alerts.repository
# (_RUNNING_RECLAIM_MINUTES/_PENDING_RECLAIM_MINUTES) — cohérence transverse
# déjà établie dans ce dépôt pour cette notion de « probablement planté ».
_RUNNING_RECLAIM_MINUTES = 60


def create_job(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    source_key: str,
    filename: str,
    collection_title: str,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None = None,
) -> IngestionJob:
    job = IngestionJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_by=created_by,
        status="pending",
        source_key=source_key,
        filename=filename,
        collection_title=collection_title,
        lat_field=lat_field,
        lon_field=lon_field,
        layer_name=layer_name,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> IngestionJob | None:
    return session.scalar(
        select(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.tenant_id == tenant_id)
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


def reclaim_stuck_jobs(
    session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES
) -> list[str]:
    """Marque "error" tout ingestion_jobs resté "running" plus vieux que
    older_than_minutes — même contrat que export_repo.reclaim_stuck_jobs/
    appexport_repo.reclaim_stuck_jobs (GAP-56.3, SP-49). IngestionJob n'a pas
    de colonne started_at (contrairement à ExportJob/AppExportJob) : ancré
    sur updated_at (onupdate=_now, cf. app/ingestion/models.py), que
    mark_running() bumpe déjà à l'entrée en "running" — un job qui reste
    "running" sans jamais atteindre mark_done/mark_error ne voit plus
    updated_at bouger, ce qui lui donne exactement le même rôle qu'un
    started_at dédié pour cette réclamation. Retourne les ids réclamés.
    Cross-tenant par construction (comme app.pipelines.repository.
    list_due_pipelines/app.alerts.repository.list_due_rules) : un sweep
    périodique appelant cette fonction tourne une fois pour tous les
    tenants, pas par tenant."""
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    rows = (
        session.execute(select(IngestionJob).where(IngestionJob.status == "running"))
        .scalars()
        .all()
    )
    reclaimed: list[str] = []
    for job in rows:
        updated_at = job.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        if updated_at >= threshold:
            continue
        job.status = "error"
        job.error_message = "ingestion timed out (worker crashed or hung)"
        reclaimed.append(job.id)
    session.flush()
    return reclaimed
