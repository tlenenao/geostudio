# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate : télécharge l'upload brut en scratch local, le
convertit en COG (app.terrain3d.conversion), l'uploade sur S3, et — si tout
réussit — crée l'item + le BuilderConfig résultants. Toute erreur
(conversion ou inattendue) marque le job "error", jamais de job bloqué en
uploaded/converting ("zombie") — même critère que
app.tileset3d.jobs/app.ingestion.tasks. L'upload brut est purgé du bucket
dans tous les cas (succès ou échec) : rien ne le référence plus une fois la
tâche terminée."""
import logging
import os
import shutil
import tempfile

from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Terrain3DPayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.terrain3d import repository as terrain3d_repo
from app.terrain3d.conversion import Terrain3DConversionError, convert_to_cog
from app.terrain3d.storage import download_to_file, upload_file

logger = logging.getLogger(__name__)

_TERRAIN3D_SCRATCH_ROOT = "/scratch"  # même volume que qgis-worker/pipelines ; monkeypatché en test


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _terrain3d_bucket() -> str:
    return os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")


def _max_upload_bytes() -> int:
    return int(os.environ.get("CORE_TERRAIN3D_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


def _conversion_timeout_seconds() -> int:
    return int(os.environ.get("CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS", "900"))


@app.task(queue="terrain3d")
def convert_terrain3d_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    with request_scoped_session(session_factory) as session:
        job = terrain3d_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("terrain3d job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        source_key, filename, title, created_by = job.source_key, job.filename, job.title, job.created_by
        terrain3d_repo.mark_converting(session, job_id=job_id)
        session.commit()

    # Tout ce qui peut lever doit être dans le try : le job est déjà marqué
    # "converting", une exception qui s'échappe ici le laisserait zombie dans
    # cet état sans message d'erreur (même critère que le fix Task 5 pour
    # s3_client_from_env()/_terrain3d_bucket() — makedirs/mkdtemp peuvent
    # échouer pour disque plein ou permission).
    scratch_dir = None
    s3 = None
    bucket = None

    try:
        os.makedirs(_TERRAIN3D_SCRATCH_ROOT, exist_ok=True)
        scratch_dir = tempfile.mkdtemp(dir=_TERRAIN3D_SCRATCH_ROOT, prefix=f"terrain3d-{job_id}-")
        raw_path = os.path.join(scratch_dir, "raw")
        cog_path = os.path.join(scratch_dir, "cog.tif")
        s3 = s3_client_from_env()
        bucket = _terrain3d_bucket()
        content_length = s3.head_object(Bucket=bucket, Key=source_key)["ContentLength"]
        if content_length > _max_upload_bytes():
            raise Terrain3DConversionError(
                f"fichier trop volumineux ({content_length} > {_max_upload_bytes()} octets)"
            )
        download_to_file(s3, bucket=bucket, key=source_key, dest_path=raw_path)
        convert_to_cog(raw_path, cog_path, timeout_seconds=_conversion_timeout_seconds())

        converted_key = f"{tenant_id}/{job_id}/dem-cog.tif"
        upload_file(s3, bucket=bucket, key=converted_key, src_path=cog_path)

        with request_scoped_session(session_factory) as session:
            item = items_repo.create_item(
                session, tenant_id=tenant_id, owner_id=created_by,
                resource_type="terrain3d", title=title,
            )
            write_audit(
                session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title, "filename": filename},
            )
            config = BuilderConfig(
                kind="terrain3d",
                terrain3d=Terrain3DPayload(sourceKey=converted_key, originalFilename=filename),
            )
            configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
            terrain3d_repo.mark_done(session, job_id=job_id, item_id=item.id, converted_key=converted_key)
        _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    except Terrain3DConversionError as exc:
        with request_scoped_session(session_factory) as session:
            terrain3d_repo.mark_error(session, job_id=job_id, error_message=str(exc))
        if s3 is not None:
            _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("terrain3d job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            terrain3d_repo.mark_error(session, job_id=job_id, error_message=f"erreur interne : {exc}")
        if s3 is not None:
            _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    finally:
        if scratch_dir is not None:
            shutil.rmtree(scratch_dir, ignore_errors=True)


def _purge_raw_upload(s3, *, bucket: str, source_key: str, tenant_id: str, job_id: str, session_factory) -> None:
    # Un échec de purge ne doit jamais masquer l'issue réelle du job (succès
    # ou erreur) : try/except large, audit_log seulement quand la suppression
    # réussit vraiment — même discipline que app.tileset3d.jobs (précédent
    # SP-14o, purge du mode "replace").
    purged = False
    try:
        s3.delete_object(Bucket=bucket, Key=source_key)
        purged = True
    except Exception:
        logger.exception("terrain3d job %s : échec de la purge de l'upload brut (%s)", job_id, source_key)
    if purged:
        try:
            with request_scoped_session(session_factory) as session:
                write_audit(
                    session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                    action="terrain3d.purge_raw_upload", object_type="terrain3d_job", object_id=job_id,
                    payload={"sourceKey": source_key},
                )
        except Exception:
            logger.exception(
                "terrain3d job %s : échec de l'écriture d'audit pour la purge de l'upload brut (%s)",
                job_id, source_key,
            )
