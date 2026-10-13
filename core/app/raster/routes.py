# SPDX-License-Identifier: Apache-2.0
"""Rasters COG (ARC-33, ADR 0024) — montées uniquement quand CORE_RASTER_ENABLED est actif.

Une seule porte d'accès aux pixels : le cœur. TiTiler reste sur le réseau interne ; le
client ne reçoit jamais d'URL S3 (présignée ou non) pour les tuiles et ne fournit jamais
l'URL transmise à TiTiler. Autorisation = celle de l'item (`can()`), plus les limites
géographiques de la collection de référence du raster (fail-closed : une tuile ne peut
pas être découpée, un lecteur limité reçoit 403)."""

import logging
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import rasterio
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.introspection import hide_sensitive_columns
from app.collections.models import Collection
from app.collections.routes import get_collection_for_read, get_introspector
from app.collections.sensitive import unmask_for_owner
from app.configs.geo_limits_dep import get_request_geo_limits
from app.configs.guest_access import GuestActor, can_read_item, get_share_link_actor, read_tenant_id
from app.db import get_session
from app.features.routes import get_features_repo, get_masked_for_user, get_rls_scope
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.quotas.service import enforce_storage_quota
from app.raster import repository as repo
from app.raster import zonal
from app.raster.models import RasterAsset
from app.raster.schemas import (
    RasterInfo,
    RasterJobStatus,
    RasterPresignRequest,
    RasterPresignResponse,
    RasterUploadCreate,
    RasterUploadCreated,
    ZonalStatsItem,
    ZonalStatsRequest,
    ZonalStatsResponse,
)
from app.roles.guards import has_privilege, require_privilege
from app.roles.privileges import Privilege
from app.sharing.geo_limits import refuse_if_geo_limited
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_ZOOM = 24
# Seuls paramètres de rendu relayés à TiTiler (liste blanche, valeurs validées).
_RENDER_PARAMS = {
    "rescale": re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$"),
    "colormap_name": re.compile(r"^[a-z0-9_]{1,40}$"),
    "bidx": re.compile(r"^\d+(,\d+){0,2}$"),
}


def get_raster_bucket() -> str:
    return os.environ.get("S3_RASTER_BUCKET", "geostudio-raster")


def get_titiler_url() -> str:
    return os.environ.get("TITILER_URL", "http://titiler:8000")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.raster.jobs import ingest_raster_task

        ingest_raster_task.defer(job_id=job_id, tenant_id=tenant_id)

    return deferrer


RasterOpener = Callable[[RasterAsset], Any]  # asset -> context manager rasterio dataset


def get_raster_opener(bucket: str = Depends(get_raster_bucket)) -> RasterOpener:
    """Ouvre le COG via /vsis3/ (GDAL), jamais via une URL fournie par l'appelant."""

    @contextmanager
    def opener(asset: RasterAsset) -> Iterator[Any]:
        endpoint = os.environ["S3_ENDPOINT_URL"]
        host = endpoint.split("://", 1)[-1].rstrip("/")
        with rasterio.Env(
            AWS_S3_ENDPOINT=host,
            AWS_HTTPS="YES" if endpoint.startswith("https") else "NO",
            AWS_VIRTUAL_HOSTING="FALSE",
            AWS_ACCESS_KEY_ID=os.environ["S3_ACCESS_KEY"],
            AWS_SECRET_ACCESS_KEY=os.environ["S3_SECRET_KEY"],
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        ):
            with rasterio.open(f"/vsis3/{bucket}/{asset.source_key}") as ds:
                yield ds

    return opener


# --- ingestion ----------------------------------------------------------------


def _check_limit_collection(session: Session, user: User, collection_id: str | None) -> None:
    if collection_id is None:
        return
    # 404 avant 403 : la collection doit être lisible par l'auteur de l'upload.
    get_collection_for_read(session, user, collection_id)


@router.post("/raster/uploads/presign", response_model=RasterPresignResponse)
def presign_raster_upload(
    body: RasterPresignRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_raster_bucket),
) -> RasterPresignResponse:
    require_privilege(session, user, Privilege.CATALOG_MANAGE.value)
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type=body.contentType)
    return RasterPresignResponse(uploadUrl=url, key=key)


@router.post("/raster/uploads", response_model=RasterUploadCreated, status_code=201)
def create_raster_upload(
    body: RasterUploadCreate,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_raster_bucket),
) -> RasterUploadCreated:
    require_privilege(session, user, Privilege.CATALOG_MANAGE.value)
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    _check_limit_collection(session, user, body.limitCollectionId)
    # Quota de stockage (SP-58) : mesuré sur l'objet déjà téléversé, avant la ligne de job.
    enforce_storage_quota(session, s3, tenant_id=user.tenant_id, bucket=bucket, key=body.key)
    job = repo.create_job(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        source_key=body.key,
        filename=body.filename,
        title=body.title,
        limit_collection_id=body.limitCollectionId,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="raster.job_create",
        object_type="raster_job",
        object_id=job.id,
        payload={"filename": body.filename, "title": body.title},
    )
    # Commit avant de déférer ; un defer perdu est repris par sweep_raster_jobs_task.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return RasterUploadCreated(jobId=job.id)


@router.get("/raster/uploads/{job_id}", response_model=RasterJobStatus)
def get_raster_upload_job(
    job_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> RasterJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None or (
        job.created_by != user.id and not has_privilege(session, user, Privilege.DATA_MANAGE.value)
    ):
        raise HTTPException(status_code=404, detail="job not found")
    return RasterJobStatus(status=job.status, errorMessage=job.error_message, itemId=job.item_id)


# --- lecture ------------------------------------------------------------------


def _readable_asset(
    session: Session, user: User | None, guest: GuestActor | None, item_id: str
) -> RasterAsset:
    """404 si l'item est illisible OU n'est pas un raster (indistinguable d'absent)."""
    if not can_read_item(session, user, guest, item_id):
        raise HTTPException(status_code=404, detail="raster not found")
    asset = repo.get_asset(session, tenant_id=read_tenant_id(session, user, guest), item_id=item_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="raster not found")
    return asset


def _refuse_if_geo_limited(session: Session, asset: RasterAsset, limits, path: str) -> None:
    if asset.limit_collection_id is None:
        return
    col = session.get(Collection, asset.limit_collection_id)
    if col is not None:
        refuse_if_geo_limited(limits, col.table_name, path=path)


@router.get("/raster/{item_id}", response_model=RasterInfo)
def get_raster_info(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
) -> RasterInfo:
    a = _readable_asset(session, user, guest, item_id)
    return RasterInfo(
        itemId=a.item_id,
        srid=a.srid,
        bounds=a.bounds,
        width=a.width,
        height=a.height,
        dtype=a.dtype,
        nodata=a.nodata,
        bands=a.bands,
        sizeBytes=a.size_bytes,
        limitCollectionId=a.limit_collection_id,
    )


@router.get("/raster/{item_id}/tiles/{z}/{x}/{y}")
def read_raster_tile(
    item_id: str,
    z: int,
    x: int,
    y: int,
    rescale: str | None = Query(default=None),
    colormap_name: str | None = Query(default=None),
    bidx: str | None = Query(default=None),
    session: Session = Depends(get_session, scope="function"),
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    limits=Depends(get_request_geo_limits),
    bucket: str = Depends(get_raster_bucket),
    titiler_url: str = Depends(get_titiler_url),
) -> Response:
    asset = _readable_asset(session, user, guest, item_id)
    _refuse_if_geo_limited(session, asset, limits, "raster tiles")
    if not (0 <= z <= _MAX_ZOOM and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(status_code=404, detail="tile not found")
    params: dict[str, str] = {"url": f"s3://{bucket}/{asset.source_key}"}
    for name, value in (("rescale", rescale), ("colormap_name", colormap_name), ("bidx", bidx)):
        if value is not None:
            if not _RENDER_PARAMS[name].match(value):
                raise HTTPException(status_code=422, detail=f"invalid {name}")
            params[name] = value
    try:
        resp = httpx.get(
            f"{titiler_url.rstrip('/')}/cog/tiles/{z}/{x}/{y}.png", params=params, timeout=30.0
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="raster tile service unavailable") from exc
    if resp.status_code == 404:  # hors emprise : cas nominal d'une source raster MapLibre
        raise HTTPException(status_code=404, detail="tile not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="raster tile service error")
    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _polygons(geojson: dict) -> list[tuple[str | int | None, dict]]:
    """Polygones (id, géométrie) d'un FeatureCollection/Feature/géométrie GeoJSON."""
    t = geojson.get("type")
    if t == "FeatureCollection":
        feats = geojson.get("features")
        if not isinstance(feats, list):
            raise HTTPException(status_code=422, detail="invalid FeatureCollection")
        items = [(f.get("id"), f.get("geometry")) for f in feats if isinstance(f, dict)]
    elif t == "Feature":
        items = [(geojson.get("id"), geojson.get("geometry"))]
    else:
        items = [(None, geojson)]
    out = []
    for fid, g in items:
        if not isinstance(g, dict) or g.get("type") not in ("Polygon", "MultiPolygon"):
            raise HTTPException(status_code=422, detail="only Polygon/MultiPolygon are supported")
        out.append((fid, g))
    return out


@router.post("/raster/{item_id}/zonal-stats", response_model=ZonalStatsResponse)
def raster_zonal_stats(
    item_id: str,
    body: ZonalStatsRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    limits=Depends(get_request_geo_limits),
    opener: RasterOpener = Depends(get_raster_opener),
    introspect=Depends(get_introspector),
    repo_features=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> ZonalStatsResponse:
    asset = _readable_asset(session, user, None, item_id)
    _refuse_if_geo_limited(session, asset, limits, "raster zonal statistics")
    if body.geojson is not None:
        polys = _polygons(body.geojson)
    else:
        # Polygones d'une collection : même porte de lecture, RLS, limites et masquage
        # que GET /collections/{id}/items.
        col = get_collection_for_read(session, user, body.collectionId)
        masked = unmask_for_owner(masked, user, col)
        info = introspect(session, col.table_name)
        if masked:
            info = hide_sensitive_columns(info, col.sensitive_fields)
        with rls(session, col.tenant_id, masked=masked):
            page = repo_features.select_features(session, info, limit=zonal.MAX_POLYGONS + 1)
        polys = [
            (f.get("id"), f["geometry"])
            for f in page.features
            if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")
        ]
    if len(polys) > zonal.MAX_POLYGONS:
        raise HTTPException(status_code=422, detail=f"too many polygons (max {zonal.MAX_POLYGONS})")
    try:
        with opener(asset) as ds:
            stats = zonal.zonal_stats(ds, [g for _, g in polys], band=body.band, stats=body.stats)
    except zonal.ZonalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="raster.zonal_stats",
        object_type="item",
        object_id=item_id,
        payload={"polygons": len(polys), "band": body.band},
    )
    return ZonalStatsResponse(
        count=len(polys),
        results=[ZonalStatsItem(id=fid, stats=s) for (fid, _), s in zip(polys, stats, strict=True)],
    )
