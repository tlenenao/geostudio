# SPDX-License-Identifier: Apache-2.0
"""Export asynchrone d'une collection (REV-283e) : relit les entités par pages
keyset sous `rls_scope` (rôle masqué si `job.masked`, GAP-22), sérialise,
téléverse dans le bucket des exports, notifie (best-effort, bloc séparé du
commit de statut — SP-39). Toute erreur finit `failed`, jamais zombie."""

import logging
import os

from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format
from app.collections import repository as collections_repo
from app.collections.introspection import hide_sensitive_columns
from app.collections.introspection_pg import introspect_table
from app.collections.routes import get_collection_for_read
from app.dataexport import repository as repo
from app.db import request_scoped_session
from app.features import repository as features_repo
from app.features.rls import rls_scope
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.jobs import app
from app.jobs.common import notify_best_effort, session_factory
from app.users.models import User

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000


def exports_bucket() -> str:
    return os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _build_file(factory, job) -> tuple[bytes, str, str]:
    """(contenu, nom de fichier, titre de collection). Lève sur toute anomalie."""
    with request_scoped_session(factory) as session:
        user = session.get(User, job.requested_by)
        if user is None:
            raise LookupError("requesting user not found")
        col = collections_repo.get_collection(
            session, tenant_id=job.tenant_id, collection_id=job.collection_id
        )
        if col is None:
            raise LookupError("collection not found")
        # can() revérifié à l'exécution : un droit retiré entre-temps = échec.
        get_collection_for_read(session, user, job.collection_id)
        info = introspect_table(session, col.table_name)
        if job.masked:
            info = hide_sensitive_columns(info, col.sensitive_fields)
        q = job.query or {}
        bbox = tuple(q["bbox"]) if q.get("bbox") else None
        job_max = repo.export_job_max()
        features: list[dict] = []
        cursor = None
        while True:
            with rls_scope(session, job.tenant_id, masked=job.masked):
                page = features_repo.select_features(
                    session,
                    info,
                    limit=PAGE_SIZE,
                    offset=0,
                    bbox=bbox,
                    geom_intersects=q.get("geomIntersects"),
                    filters=q.get("filters") or None,
                    after=cursor,
                    count_mode="none",
                )
            features.extend(page.features)
            if len(features) > job_max:
                raise ValueError(f"too many entities matched (max {job_max}), refine your filters")
            cursor = page.next_cursor
            if cursor is None:
                break
        title = col.title
    # ponytail: tout en mémoire, plafonné par CORE_EXPORT_JOB_MAX ; passer en flux
    # si gpkg/xlsx dépassent la RAM du worker.
    if job.format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=job.format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=job.format)
    return content, export_filename(title, format=job.format), title


def _notify(factory, job, *, title: str, status: str, error: str | None = None) -> None:
    notify_best_effort(
        factory,
        tenant_id=job.tenant_id,
        recipient_user_id=job.requested_by,
        kind="data_export",
        status=status,
        item_id=None,
        item_resource_type=None,
        item_title=title,
        error=error,
    )


@app.task(queue="dataexport")
def run_collection_export(job_id: str, tenant_id: str) -> None:
    factory = session_factory()
    with request_scoped_session(factory) as session:
        job = repo.get_job(session, job_id, tenant_id)
        if job is None:
            logger.error("collection export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        if not repo.mark_running(session, job_id):
            logger.warning("collection export job %s non prenable", job_id)
            return
        session.expunge(job)
    title = job.collection_id
    try:
        content, filename, title = _build_file(factory, job)
        key = f"{tenant_id}/data-exports/{job_id}.{job.format}"
        bucket = exports_bucket()
        s3 = s3_client_from_env()
        ensure_uploads_bucket(s3, bucket)
        s3.put_object(
            Bucket=bucket, Key=key, Body=content, ContentType=EXPORT_MEDIA_TYPES[job.format]
        )
        with request_scoped_session(factory) as session:
            repo.mark_done(session, job_id, result_key=key, filename=filename)
    except Exception as exc:
        logger.exception("collection export job %s : échec", job_id)
        with request_scoped_session(factory) as session:
            repo.mark_failed(session, job_id, str(exc))
        _notify(factory, job, title=title, status="failure", error=str(exc))
        return
    _notify(factory, job, title=title, status="success")
