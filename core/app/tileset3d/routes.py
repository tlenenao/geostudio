# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de tilesets 3D Tiles — montées uniquement
quand CORE_TILESET3D_ENABLED est actif (app.main, à la construction de
l'app, même patron que app.pipelines/app.export). Le proxy de lecture
(GET /tileset3d/{item_id}/{path}) est ajouté dans ce même module en Task 6."""
import logging
import os
import uuid
import zipfile
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
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

logger = logging.getLogger(__name__)

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


def _max_proxy_read_bytes() -> int:
    # Plafond DÉCOUPLÉ de CORE_TILESET3D_MAX_ENTRY_BYTES (validation, 2 Gio
    # par défaut, app.tileset3d.jobs) : un zip peut déclarer honnêtement une
    # entrée aussi grosse que le plafond de validation (zipfile borne sa
    # décompression sur file_size, donc pas besoin de mentir) — servir cette
    # taille intégralement en mémoire à chaque requête proxy resterait un
    # déni de service même sans aucune métadonnée mensongère (revue finale,
    # C2, round 2). Une entrée 3D Tiles réelle (.b3dm/.i3dm/.pnts/.cmpt/.glb)
    # fait typiquement quelques Mio ; ce plafond n'a donc pas besoin
    # d'approcher le plafond de validation pour rester généreux en usage
    # légitime.
    return int(os.environ.get("CORE_TILESET3D_MAX_PROXY_READ_BYTES", str(128 * 1024 * 1024)))


_READ_CHUNK_BYTES = 1024 * 1024  # 1 Mio


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

    # L'entrée est servie en flux : les tranches partent vers la réponse ASGI
    # au fur et à mesure, l'entrée décompressée n'est jamais matérialisée
    # entièrement dans le processus (au plus une tranche de _READ_CHUNK_BYTES
    # à la fois). Tout ce qui peut encore devenir un statut HTTP propre est
    # fait AVANT de construire la StreamingResponse : une fois le flux
    # commencé, les en-têtes sont partis et plus aucun code de statut n'est
    # négociable.
    max_bytes = _max_proxy_read_bytes()
    range_file = S3RangeFile(s3, bucket=bucket, key=payload.sourceKey)
    try:
        zf = zipfile.ZipFile(range_file)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        # Archive stockée corrompue/tronquée (BadZipFile), entrée chiffrée
        # (RuntimeError « File is encrypted ») ou méthode de compression non
        # supportée (NotImplementedError) : réponse propre plutôt qu'un 500
        # non typé du gestionnaire par défaut de FastAPI.
        raise HTTPException(status_code=422, detail="cannot read entry") from exc

    try:
        # `file_size` du répertoire central est le plafond que zipfile
        # applique lui-même à la décompression : une entrée qui le SUR-déclare
        # rend moins d'octets, une entrée qui le SOUS-déclare est tronquée
        # puis échoue le contrôle CRC (BadZipFile). Le comparer au plafond de
        # service permet donc de rendre un 413 propre avant d'avoir décompressé
        # le moindre octet, plutôt qu'en cours de flux.
        info = zf.getinfo(path)
        entry = zf.open(path)
    except KeyError as exc:
        zf.close()
        raise HTTPException(status_code=404, detail="entry not found") from exc
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        zf.close()
        raise HTTPException(status_code=422, detail="cannot read entry") from exc

    if info.file_size > max_bytes:
        entry.close()
        zf.close()
        raise HTTPException(status_code=413, detail="entry too large")

    try:
        # Première tranche lue synchronement : c'est elle qui déclenche la
        # décompression réelle, donc les erreurs d'archive détectables tôt
        # (CRC d'une entrée courte, méthode non supportée) redeviennent un 422
        # propre au lieu d'un flux coupé en plein vol.
        first_chunk = entry.read(_READ_CHUNK_BYTES)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        entry.close()
        zf.close()
        raise HTTPException(status_code=422, detail="cannot read entry") from exc
    except BaseException:
        entry.close()
        zf.close()
        raise

    def _iter_entry():
        total = len(first_chunk)
        try:
            yield first_chunk
            while True:
                chunk = entry.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    # Inatteignable tant que zipfile borne sa décompression sur
                    # `file_size` (déjà comparé au plafond ci-dessus) : filet de
                    # sécurité. Les en-têtes sont déjà partis, il n'y a plus de
                    # 413 possible — on coupe la connexion et on trace.
                    logger.error(
                        "tileset3d : entrée %s (item %s) dépasse %d octets en cours de flux",
                        path, item_id, max_bytes,
                    )
                    raise RuntimeError("tileset3d entry exceeded the proxy read cap mid-stream")
                yield chunk
        finally:
            entry.close()
            zf.close()

    return StreamingResponse(
        _iter_entry(), media_type=_content_type_for(path),
        headers={"Cache-Control": "private, max-age=3600"},
    )
