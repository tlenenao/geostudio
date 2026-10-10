# SPDX-License-Identifier: Apache-2.0
"""Export asynchrone d'une collection (REV-283e) : démarrage (appelé par la route
`export/items` de features, injecté dans main.py) + statut avec lien présigné."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections.routes import get_collection_for_read
from app.dataexport import repository as repo
from app.dataexport.jobs import exports_bucket, run_collection_export
from app.db import get_session
from app.ingestion.routes import get_s3_client  # même dépendance que export/routes.py
from app.ingestion.storage import generate_presigned_get_url
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.users.models import User

logger = logging.getLogger(__name__)
router = APIRouter()


def defer_export(job_id: str, tenant_id: str) -> None:
    run_collection_export.defer(job_id=job_id, tenant_id=tenant_id)


def start_export(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    user_id: str,
    fmt: str,
    masked: bool,
    query: dict,
    defer=defer_export,
) -> str:
    job = repo.create_job(
        session,
        tenant_id=tenant_id,
        collection_id=collection_id,
        requested_by=user_id,
        fmt=fmt,
        masked=masked,
        query=query,
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user_id,
        actor_kind="user",
        action="export.run",
        object_type="collection",
        object_id=collection_id,
        payload={"format": fmt, "mode": "items", "async": True, "jobId": job.id},
    )
    session.commit()  # commit avant de déférer, sinon le worker ne voit pas la ligne
    try:
        defer(job.id, tenant_id)
    except Exception:
        # La ligne reste `pending` : reprise par le balayage périodique (piège n°14).
        logger.exception("collection export job %s : defer échoué", job.id)
    return job.id


def default_starter(session: Session, **kwargs) -> str:
    return start_export(session, **kwargs)


def _may_see(session: Session, user: User, job) -> bool:
    # GAP-22 : le fichier d'un job non masqué contient les colonnes sensibles ;
    # le demandeur lui-même doit encore y avoir droit (rôle rétrogradé depuis).
    if not (job.masked or has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)):
        return False
    return job.requested_by == user.id or has_privilege(
        session, user, Privilege.TASKS_VIEW_ALL.value
    )


class CollectionExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None = None
    error: str | None = None
    filename: str | None = None


def get_exports_bucket() -> str:  # surchargeable, comme export/routes.py
    return exports_bucket()


@router.post(
    "/collections/{collection_id}/export/jobs/{job_id}/cancel",
    response_model=CollectionExportJobStatus,
)
def cancel_collection_export_job(
    collection_id: str,
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> CollectionExportJobStatus:
    """D6 : annule un export asynchrone en attente ou en cours. Même autorisation
    que la lecture du statut, mais l'annulation reste réservée au demandeur ou à
    `data.manage` (pas `tasks.view_all`) ; idempotent ; 409 si déjà terminé."""
    job = repo.get_job(session, job_id, user.tenant_id)
    if job is None or job.collection_id != collection_id or not _may_see(session, user, job):
        raise HTTPException(status_code=404, detail="export job not found")
    # Annuler n'est pas lire : demandeur ou data.manage (comme l'annulation d'import),
    # jamais un simple tasks.view_all.
    if job.requested_by != user.id and not has_privilege(
        session, user, Privilege.DATA_MANAGE.value
    ):
        raise HTTPException(status_code=404, detail="export job not found")
    get_collection_for_read(session, user, collection_id)
    if job.status != "cancelled":
        if job.status in ("done", "failed") or not repo.request_cancel(session, job_id):
            session.rollback()  # terminé entre-temps : rien annulé, pas d'audit
            raise HTTPException(status_code=409, detail="export job already finished")
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="export.cancel",
            object_type="collection",
            object_id=collection_id,
            payload={"jobId": job_id},
        )
        session.commit()
        session.refresh(job)
    return CollectionExportJobStatus(
        id=job.id, status=job.status, error=job.error, filename=job.filename
    )


@router.get(
    "/collections/{collection_id}/export/jobs/{job_id}", response_model=CollectionExportJobStatus
)
def get_collection_export_job(
    collection_id: str,
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_exports_bucket),
) -> CollectionExportJobStatus:
    job = repo.get_job(session, job_id, user.tenant_id)
    if job is None or job.collection_id != collection_id or not _may_see(session, user, job):
        raise HTTPException(status_code=404, detail="export job not found")
    # Lecture de la collection revérifiée (404 si le droit a été retiré depuis).
    get_collection_for_read(session, user, collection_id)
    url = None
    if job.status == "done" and job.result_key:
        url = generate_presigned_get_url(
            s3, bucket=bucket, key=job.result_key, filename=job.filename
        )
    return CollectionExportJobStatus(
        id=job.id, status=job.status, resultUrl=url, error=job.error, filename=job.filename
    )
