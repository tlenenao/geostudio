import os
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion import repository as repo
from app.ingestion.schemas import (
    IngestionJobCreate, IngestionJobCreated, IngestionJobStatus,
    PresignRequest, PresignResponse,
)
from app.ingestion.storage import (
    ensure_uploads_bucket, generate_presigned_put_url,
)
from app.ingestion.tasks import run_ingestion_task
from app.users.models import User

router = APIRouter()


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


def get_uploads_bucket() -> str:
    return os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")


def get_task_deferrer() -> Callable[[str, str], None]:
    def deferrer(job_id: str, tenant_id: str) -> None:
        run_ingestion_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/uploads/presign", response_model=PresignResponse)
def presign_upload(
    body: PresignRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_uploads_bucket),
) -> PresignResponse:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(
        s3, bucket=bucket, key=key, content_type=body.contentType
    )
    return PresignResponse(uploadUrl=url, key=key)


@router.post("/uploads", response_model=IngestionJobCreated, status_code=201)
def create_upload_job(
    body: IngestionJobCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> IngestionJobCreated:
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id, source_key=body.key,
        filename=body.filename, collection_title=body.collectionTitle,
        lat_field=body.latField, lon_field=body.lonField,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="ingestion.job_create", object_type="ingestion_job", object_id=job.id,
        payload={"filename": body.filename, "collectionTitle": body.collectionTitle},
    )
    # Commit avant de déférer : procrastinate insère la tâche via sa propre
    # connexion, hors de cette transaction SQLAlchemy — un worker pourrait la
    # ramasser avant le commit implicite de fin de requête et ne pas trouver
    # la ligne ingestion_jobs (job "zombie", l'inverse du critère
    # d'acceptation SP-6a). Commit explicite ici pour que la ligne soit
    # visible avant que la tâche n'existe.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return IngestionJobCreated(jobId=job.id)


@router.get("/uploads/{job_id}", response_model=IngestionJobStatus)
def get_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IngestionJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestionJobStatus(
        status=job.status, errorMessage=job.error_message,
        collectionId=job.collection_id, itemId=job.item_id,
    )
