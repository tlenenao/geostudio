# SPDX-License-Identifier: Apache-2.0
import os
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.dataexport.models import CollectionExportJob

_TERMINAL = ("done", "failed")


def export_sync_max() -> int:
    """Au-delà (total exact), `export/items` répond 202 au lieu d'un fichier."""
    return int(os.environ.get("CORE_EXPORT_SYNC_MAX") or "100000")


def export_job_max() -> int:
    """Plafond d'entités d'un export asynchrone (413 / job `failed` au-delà)."""
    return int(os.environ.get("CORE_EXPORT_JOB_MAX") or "500000")


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
        .values(status="running")
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(session: Session, job_id: str, *, result_key: str, filename: str) -> None:
    session.execute(
        update(CollectionExportJob)
        .where(CollectionExportJob.id == job_id, CollectionExportJob.status.notin_(_TERMINAL))
        .values(status="done", result_key=result_key, filename=filename)
    )
    session.flush()


def mark_failed(session: Session, job_id: str, error: str) -> None:
    session.execute(
        update(CollectionExportJob)
        .where(CollectionExportJob.id == job_id, CollectionExportJob.status.notin_(_TERMINAL))
        .values(status="failed", error=error)
    )
    session.flush()
