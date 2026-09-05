# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de terrain DEM — montées uniquement quand
CORE_TERRAIN3D_ENABLED est actif (app.main, même patron que
app.pipelines/app.tileset3d). Inclut le proxy de lecture authentifié
(GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png), qui vérifie can() puis
relaie vers TiTiler (réseau interne, jamais une URL fournie par
l'appelant)."""

import logging
import os
import uuid
from collections.abc import Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.items import repository as items_repo
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.sharing.authorization import can
from app.terrain3d import repository as repo
from app.terrain3d.schemas import (
    Terrain3DJobStatus,
    Terrain3DPresignRequest,
    Terrain3DPresignResponse,
    Terrain3DUploadCreate,
    Terrain3DUploadCreated,
)
from app.users.models import User

logger = logging.getLogger(__name__)

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
    url = generate_presigned_put_url(
        s3,
        bucket=bucket,
        key=key,
        content_type=body.contentType or "application/octet-stream",
    )
    return Terrain3DPresignResponse(uploadUrl=url, key=key)


@router.post("/terrain3d/uploads", response_model=Terrain3DUploadCreated, status_code=201)
def create_terrain3d_upload(
    body: Terrain3DUploadCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> Terrain3DUploadCreated:
    # SP-42, revue des lots de correctifs 2/3bis (point 1, Critical) : cette
    # route ne consultait jusqu'ici que get_current_user — aucun privilège —
    # alors que le job qu'elle crée aboutit (convert_terrain3d_task,
    # app.terrain3d.jobs) à configs_repo.create_config(kind="terrain3d"),
    # mappé sur catalog.manage (app.roles.kind_registry::privilege_for_kind).
    # Un rôle « Lecteur » (0 privilège) obtenait donc 201 ici puis devenait
    # propriétaire d'une config, exactement le trou fermé sur
    # POST /configs par eafb02cc. Réutilise le mapping existant (single
    # source of truth), pas une règle parallèle.
    require_privilege(session, user, privilege_for_kind("terrain3d"))
    # Même garde confused-deputy que app.ingestion.routes.create_upload_job :
    # la clé est censée venir du présigné ci-dessus, toujours préfixée par le
    # tenant de l'appelant.
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    job = repo.create_job(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        source_key=body.key,
        filename=body.filename,
        title=body.title,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="terrain3d.job_create",
        object_type="terrain3d_job",
        object_id=job.id,
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


def get_titiler_url() -> str:
    return os.environ.get("TITILER_URL", "http://titiler:8000")


@router.get("/terrain3d/{item_id}/tiles/{z}/{x}/{y}.png")
def read_terrain3d_tile(
    item_id: str,
    z: int,
    x: int,
    y: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    bucket: str = Depends(get_terrain3d_bucket),
    titiler_url: str = Depends(get_titiler_url),
) -> Response:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.terrain3d is None:
        raise HTTPException(status_code=404, detail="terrain not found")
    source_key = config.config.terrain3d.sourceKey

    try:
        resp = httpx.get(
            f"{titiler_url.rstrip('/')}/cog/tiles/{z}/{x}/{y}.png",
            params={"url": f"s3://{bucket}/{source_key}", "algorithm": "terrarium"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="terrain tile service unavailable") from exc

    # TiTiler répond 404 (TileOutsideBounds) pour toute tuile hors de
    # l'emprise du DEM — cas parfaitement normal : une source raster-dem
    # MapLibre demande les tuiles de tout le viewport, donc un DEM régional
    # en génère un flux continu. Les traduire en 502 ferait passer le
    # fonctionnement nominal pour une panne serveur. 502 reste réservé à
    # l'indisponibilité réelle (except httpx.HTTPError ci-dessus) et aux
    # statuts vraiment inattendus.
    if resp.status_code == 404:
        # TiTiler renvoie aussi 404 pour un endpoint /vsis3/ mal résolu (GDAL
        # ne distingue pas "hors emprise" de "objet S3 introuvable/injoignable")
        # — loggé pour permettre de distinguer les deux cas en observabilité,
        # sans changer le code HTTP renvoyé au client (cf. Manual acceptance
        # checks du plan, point 3).
        logger.warning(
            "terrain3d tile proxy: TiTiler a répondu 404 pour %s (item %s)", source_key, item_id
        )
        raise HTTPException(status_code=404, detail="tile not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="terrain tile service error")

    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
