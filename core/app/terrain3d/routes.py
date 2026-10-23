# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de terrain DEM — montées uniquement quand
CORE_TERRAIN3D_ENABLED est actif (app.main, même patron que
app.pipelines/app.tileset3d). Inclut le proxy de lecture authentifié
(GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png), qui vérifie can() puis
relaie vers TiTiler (réseau interne, jamais une URL fournie par
l'appelant)."""

import logging
import os
import re
import uuid
from collections.abc import Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.guest_access import GuestActor, can_read_item, get_share_link_actor
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.jobs.defer import defer_resilient
from app.quotas.service import enforce_storage_quota
from app.roles.guards import has_privilege, require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege
from app.terrain3d import repository as repo
from app.terrain3d.schemas import (
    Terrain3DJobStatus,
    Terrain3DPresignRequest,
    Terrain3DPresignResponse,
    Terrain3DUploadCreate,
    Terrain3DUploadCreated,
)
from app.tile_proxy import TileProxyBusyError, fetch_tile
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


def get_terrain3d_bucket() -> str:
    return os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.terrain3d.jobs import convert_terrain3d_task

        defer_resilient(lambda: convert_terrain3d_task.defer(job_id=job_id, tenant_id=tenant_id))

    return deferrer


@router.post("/terrain3d/uploads/presign", response_model=Terrain3DPresignResponse)
def presign_terrain3d_upload(
    body: Terrain3DPresignRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_terrain3d_bucket),
) -> Terrain3DPresignResponse:
    # REV-002 : cette route ne consultait jusqu'ici que get_current_user —
    # aucun privilège — alors que create_terrain3d_upload (qui suit
    # forcément dans tout flux réel) exige déjà ce même privilège. Un
    # Lecteur (0 privilège) obtenait donc une URL S3 présignée réelle sans
    # jamais pouvoir compléter le job, mais en consommant du stockage S3
    # sans aucun privilège.
    require_privilege(session, user, privilege_for_kind("terrain3d"))
    ensure_uploads_bucket(s3, bucket)
    from app.terrain3d.jobs import _max_upload_bytes  # import paresseux, comme la tâche

    if body.size > _max_upload_bytes():
        raise HTTPException(status_code=413, detail="file too large")
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    url = generate_presigned_put_url(
        s3,
        bucket=bucket,
        key=key,
        content_type=body.contentType or "application/octet-stream",
        content_length=body.size,
    )
    return Terrain3DPresignResponse(uploadUrl=url, key=key)


@router.post("/terrain3d/uploads", response_model=Terrain3DUploadCreated, status_code=201)
def create_terrain3d_upload(
    body: Terrain3DUploadCreate,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_terrain3d_bucket),
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
    # Forme imposée `{tenant}/{uuid hex}/{nom}` (celle du presign). `dem-cog.tif` est le nom
    # des COG convertis : sinon un appelant ferait copier puis supprimer le DEM d'un tiers
    # (jobs.py purge la source dans tous les cas). Même patron que raster/routes.py.
    key_ok = re.fullmatch(rf"{re.escape(user.tenant_id)}/[0-9a-f]{{32}}/([^/]+)", body.key)
    if key_ok is None or key_ok.group(1) in ("dem-cog.tif", "..") or ".." in key_ok.group(1):
        raise HTTPException(status_code=400, detail="invalid upload key")
    if repo.key_in_use(session, tenant_id=user.tenant_id, key=body.key):
        raise HTTPException(status_code=409, detail="upload key already used")
    # SP-58 Tâche 5 (GAP-73/GAP-11) : cette route ne connaissait jusqu'ici
    # pas la taille de l'objet déjà téléversé (upload direct présigné, pas
    # de s3=Depends ici avant cette tâche) — head_object est le seul moyen
    # de l'apprendre, même patron que confirm_attachment. Avant la création
    # du job (fail fast, pas de ligne orpheline).
    enforce_storage_quota(session, s3, tenant_id=user.tenant_id, bucket=bucket, key=body.key)
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
    try:
        defer_task(job.id, user.tenant_id)
    except HTTPException:  # 503 : file indisponible, le job n'est pas laissé orphelin
        repo.mark_enqueue_failed(session, job_id=job.id)
        session.commit()
        raise
    return Terrain3DUploadCreated(jobId=job.id)


@router.get("/terrain3d/uploads/{job_id}", response_model=Terrain3DJobStatus)
def get_terrain3d_upload_job(
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> Terrain3DJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    # Lisible par son initiateur ou un porteur de data.manage (patron d'ingestion, c01-012).
    if job is None or (
        job.created_by != user.id and not has_privilege(session, user, Privilege.DATA_MANAGE.value)
    ):
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
    session: Session = Depends(get_session, scope="function"),
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    bucket: str = Depends(get_terrain3d_bucket),
    titiler_url: str = Depends(get_titiler_url),
) -> Response:
    if not can_read_item(session, user, guest, item_id):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.terrain3d is None:
        raise HTTPException(status_code=404, detail="terrain not found")
    source_key = config.config.terrain3d.sourceKey
    # AUD-056 : connexion rendue avant l'appel sortant (cf. raster/routes.py).
    session.commit()

    try:
        status, content = fetch_tile(
            f"{titiler_url.rstrip('/')}/cog/tiles/{z}/{x}/{y}.png",
            {"url": f"s3://{bucket}/{source_key}", "algorithm": "terrarium"},
        )
    except TileProxyBusyError as exc:
        raise HTTPException(
            status_code=503, detail="terrain tile service busy", headers={"Retry-After": "2"}
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="terrain tile service unavailable") from exc

    # TiTiler répond 404 (TileOutsideBounds) pour toute tuile hors de
    # l'emprise du DEM — cas parfaitement normal : une source raster-dem
    # MapLibre demande les tuiles de tout le viewport, donc un DEM régional
    # en génère un flux continu. Les traduire en 502 ferait passer le
    # fonctionnement nominal pour une panne serveur. 502 reste réservé à
    # l'indisponibilité réelle (except httpx.HTTPError ci-dessus) et aux
    # statuts vraiment inattendus.
    if status == 404:
        # TiTiler renvoie aussi 404 pour un endpoint /vsis3/ mal résolu (GDAL
        # ne distingue pas "hors emprise" de "objet S3 introuvable/injoignable")
        # — loggé pour permettre de distinguer les deux cas en observabilité,
        # sans changer le code HTTP renvoyé au client (cf. Manual acceptance
        # checks du plan, point 3).
        logger.warning(
            "terrain3d tile proxy: TiTiler a répondu 404 pour %s (item %s)", source_key, item_id
        )
        raise HTTPException(status_code=404, detail="tile not found")
    if status != 200:
        raise HTTPException(status_code=502, detail="terrain tile service error")

    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
