# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate : valide le zip complété (S3RangeFile, jamais un
téléchargement complet) et, si valide, crée l'item + le BuilderConfig
résultants. Toute erreur (validation ou inattendue) marque le job "error",
jamais de job bloqué en pending/finalizing ("zombie") — même critère que
app.ingestion.tasks/app.export.jobs."""
import logging
import os

from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.tileset3d import repository as tileset3d_repo
from app.tileset3d.storage import S3RangeFile, Tileset3DValidationError, validate_tileset_zip

logger = logging.getLogger(__name__)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _tileset3d_bucket() -> str:
    return os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")


def _max_entries() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_ENTRIES", "20000"))


def _max_total_bytes() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_TOTAL_BYTES", str(20 * 1024 * 1024 * 1024)))


def _max_entry_bytes() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_ENTRY_BYTES", str(2 * 1024 * 1024 * 1024)))


@app.task(queue="tileset3d")
def finalize_tileset3d_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    with request_scoped_session(session_factory) as session:
        job = tileset3d_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("tileset3d job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        source_key, filename, title, created_by = job.source_key, job.filename, job.title, job.created_by

    try:
        s3 = s3_client_from_env()
        range_file = S3RangeFile(s3, bucket=_tileset3d_bucket(), key=source_key)
        result = validate_tileset_zip(
            range_file, max_entries=_max_entries(),
            max_total_bytes=_max_total_bytes(), max_entry_bytes=_max_entry_bytes(),
        )
        with request_scoped_session(session_factory) as session:
            item = items_repo.create_item(
                session, tenant_id=tenant_id, owner_id=created_by,
                resource_type="tileset3d", title=title,
            )
            write_audit(
                session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title, "filename": filename},
            )
            config = BuilderConfig(
                kind="tileset3d",
                tileset3d=Tileset3DPayload(
                    sourceKey=source_key, tilesetJsonPath="tileset.json",
                    totalBytes=result.total_bytes, entryCount=result.entry_count,
                ),
            )
            configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
            tileset3d_repo.mark_done(session, job_id=job_id, item_id=item.id)
    except Tileset3DValidationError as exc:
        # Le zip rejeté n'est référencé par rien (aucun item, aucun config) :
        # le purger tout de suite, sinon plusieurs Go restent dans le bucket
        # pour toujours. Un échec de purge ne doit jamais masquer l'erreur de
        # validation destinée à l'utilisateur — d'où le try/except large. La
        # purge est une écriture destructive : audit_log obligatoire quand
        # elle réussit (précédent SP-14o, purge du mode "replace"), jamais
        # quand elle échoue (pas de faux enregistrement d'un événement qui
        # n'a pas eu lieu).
        purged = False
        try:
            s3_client_from_env().delete_object(Bucket=_tileset3d_bucket(), Key=source_key)
            purged = True
        except Exception:
            logger.exception("tileset3d job %s : échec de la purge du zip rejeté (%s)", job_id, source_key)
        with request_scoped_session(session_factory) as session:
            if purged:
                write_audit(
                    session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                    action="tileset3d.purge", object_type="tileset3d_upload", object_id=job_id,
                    payload={"sourceKey": source_key, "reason": str(exc)},
                )
            tileset3d_repo.mark_error(session, job_id=job_id, error_message=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("tileset3d job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            tileset3d_repo.mark_error(session, job_id=job_id, error_message=f"erreur interne : {exc}")
