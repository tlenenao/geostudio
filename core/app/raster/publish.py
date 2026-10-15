# SPDX-License-Identifier: Apache-2.0
"""Publication d'un raster dérivé par un pipeline (voie FME F1) : GeoTIFF local -> COG ->
bucket raster -> item `raster` + `raster_assets`. Même chaîne que l'ingestion de
`app.raster.jobs` (validation/conversion COG, quota de stockage, quota d'items porté par
`create_item`, audit `item.create`), mais synchrone dans la session du run : `flush`, jamais
`commit` : un échec ultérieur du run annule l'item, et `run_pipeline` supprime alors les COG
publiés par le run (`RUN_PUBLISHED_KEYS`, sinon orphelins comptés au quota de stockage) et
n'écrit plus aucun point de reprise après une publication (une reprise rechargerait un
`raster_item_id` annulé — revue finale FME, I2). Droit requis : `catalog.manage`, comme
l'upload REST d'un raster."""

import logging
import os
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.quotas.service import enforce_storage_quota
from app.raster import ingest
from app.raster.models import RasterAsset
from app.raster.service import raster_bucket
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.terrain3d.storage import upload_file

# Clés S3 des COG publiés pendant le run courant (posé par `run_pipeline`) ; None hors run.
RUN_PUBLISHED_KEYS: ContextVar[list[str] | None] = ContextVar("run_published_keys", default=None)


class RasterPublishError(ValueError):
    pass


@dataclass(frozen=True)
class Published:
    item_id: str
    width: int
    height: int
    bands: int


def _upload(session: Session, tenant_id: str, key: str, path: str) -> None:
    """Couture de test : téléverse le COG puis applique le quota de stockage (qui supprime
    l'objet en cas de refus)."""
    s3 = make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    bucket = raster_bucket()
    upload_file(s3, bucket=bucket, key=key, src_path=path)
    enforce_storage_quota(session, s3, tenant_id=tenant_id, bucket=bucket, key=key)


def delete_key(key: str) -> None:
    """Couture de test : suppression best-effort d'un COG publié (annulation d'un run)."""
    try:
        s3 = make_s3_client(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ["S3_SECRET_KEY"],
        )
        s3.delete_object(Bucket=raster_bucket(), Key=key)
    except Exception:
        logging.getLogger(__name__).warning("raster publish: objet %s non supprimé", key)


def can_publish(session: Session, user) -> bool:
    return has_privilege(session, user, Privilege.CATALOG_MANAGE.value)


def publish_raster(
    session: Session,
    user,
    *,
    tif_path: str,
    cog_path: str,
    title: str,
    limit_collection_id: str | None,
    filename: str,
    timeout_seconds: int = 300,
    keys: list[str] | None = None,
) -> Published:
    if not can_publish(session, user):
        raise RasterPublishError("privilege 'catalog.manage' required to publish a raster")
    try:
        ingest.to_cog(tif_path, cog_path, timeout_seconds=timeout_seconds)
        meta = ingest.read_metadata(cog_path)
    except ingest.RasterIngestError as exc:
        raise RasterPublishError(str(exc)) from exc
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/cog.tif"
    _upload(session, user.tenant_id, key, cog_path)
    try:
        return _record(
            session, user, key, cog_path, meta, title, limit_collection_id, filename, keys
        )
    except BaseException:
        delete_key(key)  # l'objet est compté au quota de stockage : pas d'orphelin
        raise


def _record(session, user, key, cog_path, meta, title, limit_collection_id, filename, keys):
    item = items_repo.create_item(
        session, tenant_id=user.tenant_id, owner_id=user.id, resource_type="raster", title=title
    )
    session.add(
        RasterAsset(
            item_id=item.id,
            tenant_id=user.tenant_id,
            source_key=key,
            srid=meta.srid,
            bounds=meta.bounds,
            width=meta.width,
            height=meta.height,
            dtype=meta.dtype,
            nodata=meta.nodata,
            bands=meta.bands,
            size_bytes=os.path.getsize(cog_path),
            limit_collection_id=limit_collection_id,
        )
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="item.create",
        object_type="item",
        object_id=item.id,
        payload={"title": title, "filename": filename, "op": "pipeline"},
    )
    session.flush()
    if keys is not None:
        keys.append(key)
    if (run_keys := RUN_PUBLISHED_KEYS.get()) is not None:
        run_keys.append(key)
    return Published(item.id, meta.width, meta.height, len(meta.bands))
