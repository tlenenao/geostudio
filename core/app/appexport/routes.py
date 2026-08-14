# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'export d'app (SP-18a) — montées uniquement quand
CORE_APPEXPORT_ENABLED est actif, même patron que app.export.routes."""
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.appexport import repository as appexport_repo
from app.appexport.jobs import build_app_export_task
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_SUPPORTED_MODES = {"static"}  # "connected"/"standalone" arrivent en SP-18b/c


class CreateAppExportRequest(BaseModel):
    itemId: str
    mode: str


class CreateAppExportResponse(BaseModel):
    jobId: str


class AppExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None


def _require_export_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")


def get_appexports_bucket() -> str:
    return os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        build_app_export_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/app-exports", response_model=CreateAppExportResponse, status_code=202)
def create_app_export_route(
    body: CreateAppExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> CreateAppExportResponse:
    if body.mode not in _SUPPORTED_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {sorted(_SUPPORTED_MODES)}")
    _require_export_read_access(session, user=user, item_id=body.itemId)
    job = appexport_repo.create_job(session, tenant_id=user.tenant_id, item_id=body.itemId, user_id=user.id, mode=body.mode)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="appexport.create", object_type="app_export_job", object_id=job.id,
        payload={"itemId": body.itemId, "mode": body.mode},
    )
    session.commit()  # commit avant de déférer : même raison que export_routes/run_pipeline_route
    defer_task(job.id, user.tenant_id)
    return CreateAppExportResponse(jobId=job.id)


@router.get("/app-exports/jobs/{job_id}", response_model=AppExportJobStatus)
def get_app_export_job_route(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_appexports_bucket),
) -> AppExportJobStatus:
    job = appexport_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="app export job not found")
    _require_export_read_access(session, user=user, item_id=job.item_id)
    result_url = None
    if job.status == "done" and job.result_key:
        result_url = generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)
    return AppExportJobStatus(id=job.id, status=job.status, resultUrl=result_url, error=job.error)
