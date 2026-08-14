# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de tilesets 3D Tiles — montées uniquement
quand CORE_TILESET3D_ENABLED est actif (app.main, à la construction de
l'app, même patron que app.pipelines/app.export). Le proxy de lecture
(GET /tileset3d/{item_id}/{path}) est ajouté dans ce même module en Task 6."""
import os
import uuid
import zipfile
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.tileset3d import repository as repo
from app.tileset3d.schemas import (
    Tileset3DCompleteRequest, Tileset3DJobStatus, Tileset3DPartPresignResponse,
    Tileset3DUploadCreate, Tileset3DUploadCreated,
)
from app.tileset3d.storage import S3RangeFile
from app.users.models import User

router = APIRouter()

_CONTENT_TYPES = {
    ".json": "application/json",
    ".gltf": "application/json",
    ".b3dm": "application/octet-stream",
    ".i3dm": "application/octet-stream",
    ".pnts": "application/octet-stream",
    ".cmpt": "application/octet-stream",
    ".glb": "application/octet-stream",
}


def _content_type_for(path: str) -> str:
    for ext, content_type in _CONTENT_TYPES.items():
        if path.endswith(ext):
            return content_type
    return "application/octet-stream"


def get_tileset3d_bucket() -> str:
    return os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")


def _max_entry_bytes() -> int:
    # Même variable et même défaut que app.tileset3d.jobs._max_entry_bytes :
    # le plafond appliqué à la validation doit être celui appliqué à la
    # lecture, sinon la validation ne protège rien à la lecture.
    return int(os.environ.get("CORE_TILESET3D_MAX_ENTRY_BYTES", str(2 * 1024 * 1024 * 1024)))


_READ_CHUNK_BYTES = 1024 * 1024  # 1 Mio


def _read_entry_bounded(zf: zipfile.ZipFile, path: str, *, max_bytes: int) -> bytes:
    """Lit une entrée par tranches, en s'arrêtant net dès que le cumul
    décompressé dépasse le plafond. `zf.read(path)` décompresserait tout le
    flux réel en mémoire d'abord : `info.file_size` du répertoire central est
    une métadonnée contrôlée par l'auteur du zip, jamais vérifiée
    indépendamment — un zip-bomb passerait la validation puis exploserait la
    mémoire du cœur à la première lecture."""
    with zf.open(path) as f:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = f.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail="entry too large")
            chunks.append(chunk)
        return b"".join(chunks)


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.tileset3d.jobs import finalize_tileset3d_task

        finalize_tileset3d_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/tileset3d/uploads", response_model=Tileset3DUploadCreated, status_code=201)
def create_tileset3d_upload(
    body: Tileset3DUploadCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Tileset3DUploadCreated:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    mp = s3.create_multipart_upload(Bucket=bucket, Key=key)
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id, source_key=key,
        upload_id=mp["UploadId"], filename=body.filename, title=body.title,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="tileset3d.job_create", object_type="tileset3d_job", object_id=job.id,
        payload={"filename": body.filename, "title": body.title},
    )
    session.commit()
    return Tileset3DUploadCreated(jobId=job.id)


@router.post("/tileset3d/uploads/{job_id}/parts/{part_number}/presign", response_model=Tileset3DPartPresignResponse)
def presign_tileset3d_part(
    job_id: str, part_number: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Tileset3DPartPresignResponse:
    if part_number < 1:
        raise HTTPException(status_code=422, detail="partNumber must be >= 1")
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    url = s3.generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket, "Key": job.source_key, "PartNumber": part_number, "UploadId": job.upload_id},
        ExpiresIn=900,
    )
    return Tileset3DPartPresignResponse(uploadUrl=url)


@router.post("/tileset3d/uploads/{job_id}/complete", status_code=204)
def complete_tileset3d_upload(
    job_id: str, body: Tileset3DCompleteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> None:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    s3.complete_multipart_upload(
        Bucket=bucket, Key=job.source_key, UploadId=job.upload_id,
        MultipartUpload={"Parts": [{"PartNumber": p.partNumber, "ETag": p.etag} for p in body.parts]},
    )
    repo.mark_finalizing(session, job_id=job.id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="tileset3d.upload_complete", object_type="tileset3d_job", object_id=job.id, payload={},
    )
    # Commit avant de déférer : même raison que app.ingestion.routes.create_upload_job.
    session.commit()
    defer_task(job.id, user.tenant_id)


@router.get("/tileset3d/uploads/{job_id}", response_model=Tileset3DJobStatus)
def get_tileset3d_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Tileset3DJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Tileset3DJobStatus(status=job.status, errorMessage=job.error_message, itemId=job.item_id)


@router.get("/tileset3d/{item_id}/{path:path}")
def read_tileset3d_entry(
    item_id: str, path: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Response:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.tileset3d is None:
        raise HTTPException(status_code=404, detail="tileset not found")
    payload = config.config.tileset3d

    range_file = S3RangeFile(s3, bucket=bucket, key=payload.sourceKey)
    try:
        with zipfile.ZipFile(range_file) as zf:
            data = _read_entry_bounded(zf, path, max_bytes=_max_entry_bytes())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="entry not found") from exc
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        # Archive stockée corrompue/tronquée (BadZipFile), entrée chiffrée
        # (RuntimeError « File is encrypted ») ou méthode de compression non
        # supportée (NotImplementedError) : réponse propre plutôt qu'un 500
        # non typé du gestionnaire par défaut de FastAPI.
        raise HTTPException(status_code=422, detail="cannot read entry") from exc

    return Response(
        content=data, media_type=_content_type_for(path),
        headers={"Cache-Control": "private, max-age=3600"},
    )
