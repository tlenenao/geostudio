# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de terrain DEM — montées uniquement quand
CORE_TERRAIN3D_ENABLED est actif (app.main, même patron que
app.pipelines/app.tileset3d). Le proxy de lecture
(GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png) est ajouté dans ce même
module en Task 6."""
import os
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.terrain3d import repository as repo
from app.terrain3d.schemas import (
    Terrain3DJobStatus, Terrain3DPresignRequest, Terrain3DPresignResponse,
    Terrain3DUploadCreate, Terrain3DUploadCreated,
)
from app.users.models import User

router = APIRouter()


def get_terrain3d_bucket() -> str:
    return os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.terrain3d.jobs import convert_terrain3d_task

        convert_terrain3d_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/terrain3d/uploads/presign", response_model=Terrain3DPresignResponse)
def presign_terrain3d_upload(
    body: Terrain3DPresignRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_terrain3d_bucket),
) -> Terrain3DPresignResponse:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type="application/octet-stream")
    return Terrain3DPresignResponse(uploadUrl=url, key=key)


@router.post("/terrain3d/uploads", response_model=Terrain3DUploadCreated, status_code=201)
def create_terrain3d_upload(
    body: Terrain3DUploadCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> Terrain3DUploadCreated:
    # Même garde confused-deputy que app.ingestion.routes.create_upload_job :
    # la clé est censée venir du présigné ci-dessus, toujours préfixée par le
    # tenant de l'appelant.
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id,
        source_key=body.key, filename=body.filename, title=body.title,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="terrain3d.job_create", object_type="terrain3d_job", object_id=job.id,
        payload={"filename": body.filename, "title": body.title},
    )
    # Commit avant de déférer : même raison que app.ingestion.routes.create_upload_job.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return Terrain3DUploadCreated(jobId=job.id)


@router.get("/terrain3d/uploads/{job_id}", response_model=Terrain3DJobStatus)
def get_terrain3d_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Terrain3DJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Terrain3DJobStatus(status=job.status, errorMessage=job.error_message, itemId=job.item_id)
