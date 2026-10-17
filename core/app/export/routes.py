# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'export (SP-17a) — montées uniquement quand
CORE_EXPORT_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête — même patron que app.pipelines.routes)."""

import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task

# Réutilise le placeholder générique d'app.ingestion.routes (`raise
# RuntimeError(...)` par défaut, overridé dans app.main quand S3_* est
# configuré) plutôt que d'en redéfinir un second identique ici : ce n'est
# qu'un point d'injection FastAPI overridable, sans logique spécifique à
# l'ingestion, et app.export dépend déjà d'app.ingestion.storage (revue
# SP-17a, finding Important task 7, fix round 1).
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.jobs.defer import defer_resilient
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


class CreateExportRequest(BaseModel):
    itemId: str
    format: str
    # ARC-26 / ARC-30 (PDF d'app seulement) : fiche d'une entité, ou atlas.
    entityId: str | None = Field(default=None, max_length=200)
    atlas: bool = False
    # AUD-133 : contexte analytique courant (période, emprise, cross-filter) tel
    # qu'encodé par le shell (`?ctx=`, base64url). Charset restreint : la valeur
    # est recopiée dans l'URL que le worker ouvre.
    ctx: str | None = Field(default=None, max_length=16000, pattern=r"^[A-Za-z0-9_-]+$")


class CreateExportResponse(BaseModel):
    jobId: str


class ExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None


def _require_export_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")


def get_exports_bucket() -> str:
    return os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        defer_resilient(lambda: render_export_task.defer(job_id=job_id, tenant_id=tenant_id))

    return deferrer


@router.post("/export", response_model=CreateExportResponse, status_code=202)
def create_export_route(
    body: CreateExportRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> CreateExportResponse:
    if body.format not in ("png", "pdf", "svg"):
        raise HTTPException(status_code=422, detail="format must be 'png', 'pdf' or 'svg'")
    _require_export_read_access(session, user=user, item_id=body.itemId)
    scope = f"entity:{body.entityId}" if body.entityId else ("atlas" if body.atlas else None)
    if scope is not None:
        if body.format != "pdf":
            raise HTTPException(status_code=422, detail="entityId/atlas require format 'pdf'")
        config = configs_repo.get_config_by_item(session, body.itemId)
        layout = getattr(config.config, "printLayout", None) if config else None
        if config is None or config.kind == "map" or layout is None or layout.atlas is None:
            raise HTTPException(
                status_code=422, detail="entityId/atlas require an app with printLayout.atlas"
            )
    job = export_repo.create_job(
        session,
        tenant_id=user.tenant_id,
        item_id=body.itemId,
        user_id=user.id,
        format=body.format,
        ctx=body.ctx,
        scope=scope,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="export.create",
        object_type="export_job",
        object_id=job.id,
        payload={"itemId": body.itemId, "format": body.format, "scope": scope},
    )
    # Commit avant de déférer : même raison que run_pipeline_route.
    session.commit()
    try:
        defer_task(job.id, user.tenant_id)
    except HTTPException:  # 503 : file indisponible, le job n'est pas laissé orphelin
        export_repo.mark_enqueue_failed(session, job_id=job.id)
        session.commit()
        raise
    return CreateExportResponse(jobId=job.id)


@router.get("/export/jobs/{job_id}", response_model=ExportJobStatus)
def get_export_job_route(
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_exports_bucket),
) -> ExportJobStatus:
    job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None or (
        job.user_id != user.id and not has_privilege(session, user, Privilege.DATA_MANAGE.value)
    ):
        raise HTTPException(status_code=404, detail="export job not found")
    _require_export_read_access(session, user=user, item_id=job.item_id)
    result_url = None
    if job.status == "done" and job.result_key:
        result_url = generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)
    return ExportJobStatus(id=job.id, status=job.status, resultUrl=result_url, error=job.error)


@router.post("/export/jobs/{job_id}/cancel", response_model=ExportJobStatus)
def cancel_export_job_route(
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> ExportJobStatus:
    """ARC-16 : `pending` -> `cancelled` ; `running` -> `cancel_requested` (le
    worker s'arrête avant l'envoi du résultat). 409 si déjà terminé."""
    job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None or (
        job.user_id != user.id and not has_privilege(session, user, Privilege.DATA_MANAGE.value)
    ):
        raise HTTPException(status_code=404, detail="export job not found")
    if job.status in ("cancelled", "cancel_requested"):
        return ExportJobStatus(id=job.id, status=job.status, resultUrl=None, error=job.error)
    new_status = export_repo.request_cancel(session, job_id=job_id)
    if new_status is None:
        raise HTTPException(status_code=409, detail=f"job is {job.status}, cannot be cancelled")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="export.cancel",
        object_type="export_job",
        object_id=job.id,
        payload={"status": new_status},
    )
    session.commit()
    return ExportJobStatus(id=job.id, status=new_status, resultUrl=None, error=None)
