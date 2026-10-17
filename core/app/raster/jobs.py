# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate d'ingestion raster : télécharge l'upload en scratch local, valide
(COG) ou convertit, extrait emprise/SRID/bandes/stats, téléverse le COG dans le bucket
raster, puis crée l'item + sa ligne `raster_assets`. Toute erreur marque le job « error »
(jamais zombie) ; l'upload brut est purgé dans tous les cas. Une reprise périodique
(`sweep_raster_jobs_task`) réclame les jobs perdus (commit puis defer, piège n°14)."""

import logging
import os
import shutil
import tempfile

from app.audit.writer import write_audit
from app.db import request_scoped_session
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.job_errors import INTERNAL_ERROR_MESSAGE
from app.jobs import app
from app.jobs.common import notify_best_effort
from app.jobs.engine import session_factory as common_session_factory
from app.quotas.service import QuotaExceededError, enforce_storage_quota
from app.raster import ingest
from app.raster import repository as repo
from app.raster.models import RasterAsset
from app.terrain3d.storage import download_to_file, upload_file

logger = logging.getLogger(__name__)

# Volume `etl-scratch` du service worker ; monkeypatché en test.
_RASTER_SCRATCH_ROOT = "/scratch"


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _session_factory():
    return common_session_factory()


def raster_bucket() -> str:
    return os.environ.get("S3_RASTER_BUCKET", "geostudio-raster")


def _max_upload_bytes() -> int:
    return int(os.environ.get("CORE_RASTER_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


def _conversion_timeout_seconds() -> int:
    return int(os.environ.get("CORE_RASTER_CONVERSION_TIMEOUT_SECONDS", "900"))


def run_ingest(session_factory, s3, *, job_id: str, tenant_id: str) -> None:
    """Corps testable de la tâche (S3 et fabrique de session injectés)."""
    with request_scoped_session(session_factory) as session:
        job = repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("raster job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        source_key, filename, title, created_by, limit_collection_id = (
            job.source_key,
            job.filename,
            job.title,
            job.created_by,
            job.limit_collection_id,
        )
        if not repo.mark_converting(session, job_id=job_id):
            logger.info("raster job %s non démarré : plus en file", job_id)
            return
        session.commit()

    bucket = raster_bucket()

    def _notify(status: str, item_id: str | None, error: str | None = None) -> None:
        notify_best_effort(
            session_factory,
            tenant_id=tenant_id,
            recipient_user_id=created_by,
            kind="raster",
            status=status,
            item_id=item_id,
            item_resource_type="raster" if item_id else None,
            item_title=title,
            error=error,
        )

    def _fail(message: str) -> None:
        with request_scoped_session(session_factory) as session:
            repo.mark_error(session, job_id=job_id, error_message=message)
        _notify("failure", None, message)

    scratch_dir = None
    try:
        os.makedirs(_RASTER_SCRATCH_ROOT, exist_ok=True)
        scratch_dir = tempfile.mkdtemp(dir=_RASTER_SCRATCH_ROOT, prefix=f"raster-{job_id}-")
        raw_path = os.path.join(scratch_dir, "raw")
        cog_path = os.path.join(scratch_dir, "cog.tif")
        length = s3.head_object(Bucket=bucket, Key=source_key)["ContentLength"]
        if length > _max_upload_bytes():
            raise ingest.RasterIngestError(
                f"fichier trop volumineux ({length} > {_max_upload_bytes()} octets)"
            )
        download_to_file(s3, bucket=bucket, key=source_key, dest_path=raw_path)
        ingest.to_cog(raw_path, cog_path, timeout_seconds=_conversion_timeout_seconds())
        meta = ingest.read_metadata(cog_path)
        size_bytes = os.path.getsize(cog_path)
        converted_key = f"{tenant_id}/{job_id}/cog.tif"
        upload_file(s3, bucket=bucket, key=converted_key, src_path=cog_path)
        # Le COG deflate peut dépasser le brut : recontrôle du quota (le brut, déjà converti,
        # est libéré d'abord pour ne pas être compté deux fois ; la purge du `finally` est
        # idempotente). En cas de refus, enforce_storage_quota supprime le COG.
        s3.delete_object(Bucket=bucket, Key=source_key)
        try:
            with request_scoped_session(session_factory) as session:
                enforce_storage_quota(
                    session, s3, tenant_id=tenant_id, bucket=bucket, key=converted_key
                )
        except QuotaExceededError as exc:
            raise ingest.RasterIngestError(str(exc)) from exc

        with request_scoped_session(session_factory) as session:
            item = items_repo.create_item(
                session,
                tenant_id=tenant_id,
                owner_id=created_by,
                resource_type="raster",
                title=title,
            )
            session.add(
                RasterAsset(
                    item_id=item.id,
                    tenant_id=tenant_id,
                    source_key=converted_key,
                    srid=meta.srid,
                    bounds=meta.bounds,
                    width=meta.width,
                    height=meta.height,
                    dtype=meta.dtype,
                    nodata=meta.nodata,
                    bands=meta.bands,
                    size_bytes=size_bytes,
                    limit_collection_id=limit_collection_id,
                )
            )
            write_audit(
                session,
                tenant_id=tenant_id,
                actor_id=created_by,
                actor_kind="user",
                action="item.create",
                object_type="item",
                object_id=item.id,
                payload={"title": title, "filename": filename},
            )
            repo.mark_done(session, job_id=job_id, item_id=item.id, converted_key=converted_key)
            item_id = item.id
        _notify("success", item_id)
    except ingest.RasterIngestError as exc:
        _fail(str(exc))
    except Exception:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("raster job %s : erreur inattendue", job_id)
        _fail(INTERNAL_ERROR_MESSAGE)
    finally:
        if scratch_dir is not None:
            shutil.rmtree(scratch_dir, ignore_errors=True)
        try:  # l'upload brut n'est plus référencé une fois le job terminé
            s3.delete_object(Bucket=bucket, Key=source_key)
        except Exception:
            logger.exception("raster job %s : échec de purge de l'upload brut", job_id)


@app.task(queue="raster")
def ingest_raster_task(job_id: str, tenant_id: str) -> None:
    run_ingest(_session_factory(), s3_client_from_env(), job_id=job_id, tenant_id=tenant_id)


@app.periodic(cron="*/5 * * * *")
@app.task(queue="raster", queueing_lock="sweep_raster_jobs_task")
def sweep_raster_jobs_task(timestamp: int) -> None:
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        reclaimed = [
            (j.tenant_id, j.created_by, j.title, j.error_message, j.source_key)
            for j in repo.reclaim_stuck_jobs(session)
        ]
        session.commit()
    s3 = s3_client_from_env()
    for tenant_id, user_id, title, error, raw_key in reclaimed:
        try:  # l'upload brut d'un job abandonné ne reste pas compté au quota
            s3.delete_object(Bucket=raster_bucket(), Key=raw_key)
        except Exception:
            logger.exception("raster sweep : échec de purge de %s", raw_key)
        notify_best_effort(
            factory,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            kind="raster",
            status="failure",
            item_id=None,
            item_resource_type=None,
            item_title=title,
            error=error,
        )
