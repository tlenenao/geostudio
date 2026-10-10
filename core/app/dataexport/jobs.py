# SPDX-License-Identifier: Apache-2.0
"""Export asynchrone d'une collection (REV-283e) : relit les entités par pages
keyset sous `rls_scope` (rôle masqué si `job.masked`, GAP-22), sérialise,
téléverse dans le bucket des exports, notifie (best-effort, bloc séparé du
commit de statut — SP-39). Toute erreur finit `failed`, jamais zombie."""

import logging
import os

from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    export_job_max,
    features_to_format,
)
from app.auth.dependency import is_read_only_mode
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
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
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
        # GAP-22 : verdict recalculé à l'exécution (comme alerts/pipelines) — le
        # privilège a pu être retiré depuis la création ; jamais moins strict.
        masked = job.masked or not has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
        if masked:
            info = hide_sensitive_columns(info, col.sensitive_fields)
        q = job.query or {}
        bbox = tuple(q["bbox"]) if q.get("bbox") else None
        job_max = export_job_max()
        features: list[dict] = []
        cursor = None
        while True:
            with rls_scope(session, job.tenant_id, masked=masked):
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
            done = repo.mark_done(session, job_id, result_key=key, filename=filename)
        if not done:  # repris en `failed` pendant l'envoi : l'objet serait orphelin
            logger.warning("collection export job %s terminé tardivement, objet supprimé", job_id)
            s3.delete_object(Bucket=bucket, Key=key)
            return
    except Exception as exc:
        logger.exception("collection export job %s : échec", job_id)
        with request_scoped_session(factory) as session:
            repo.mark_failed(session, job_id, str(exc))
        _notify(factory, job, title=title, status="failure", error=str(exc))
        return
    _notify(factory, job, title=title, status="success")


@app.periodic(cron="*/10 * * * *")
@app.task(queue="dataexport", queueing_lock="sweep_collection_exports_task")
def sweep_collection_exports_task(timestamp: int) -> None:
    """Reprise : `pending` dont le defer a échoué (commit puis defer, piège 14)
    redéférés ; `running` bloqués passés `failed`. mark_running rend un double
    defer inoffensif."""
    if is_read_only_mode():
        return
    factory = session_factory()
    with request_scoped_session(factory) as session:
        repo.reclaim_stuck_running(session)
        pending = repo.stale_pending_ids(session)
        session.commit()
    for job_id, tenant_id in pending:
        try:
            run_collection_export.defer(job_id=job_id, tenant_id=tenant_id)
        except Exception:
            logger.exception("collection export %s : redefer impossible", job_id)


@app.periodic(cron="17 * * * *")
@app.task(queue="dataexport", queueing_lock="purge_collection_exports_task")
def purge_expired_exports_task(timestamp: int) -> None:
    """TTL : supprime l'objet S3 puis la ligne des exports terminés expirés.
    Échec S3 = la ligne reste (nouvel essai au prochain passage)."""
    if is_read_only_mode():
        return
    factory = session_factory()
    with request_scoped_session(factory) as session:
        expired = repo.expired_terminal_jobs(session)
    s3 = s3_client_from_env() if any(k for _, k in expired) else None
    for job_id, key in expired:
        try:
            if key:
                s3.delete_object(Bucket=exports_bucket(), Key=key)  # type: ignore[union-attr]
        except Exception:
            logger.exception("collection export %s : suppression S3 impossible", job_id)
            continue
        with request_scoped_session(factory) as session:
            repo.delete_job(session, job_id)
