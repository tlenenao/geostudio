# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-18a/b/c) : guard → (statique : gèle les
DataSources ; connecté : garde la config telle quelle + embarque l'URL du
cœur ; autoporté : écrit un instantané GeoParquet local + zippe avec un
docker-compose.yml généré) → upload S3. Tourne sur le worker partagé (queue
`appexport`, pas de Chromium/Node/Docker ici — écrire un instantané local
avant de zipper n'a besoin ni de Docker ni de réseau). Toute erreur marque
le job "error", jamais un job bloqué en "running" (même critère que
app.export.jobs/app.pipelines.jobs)."""

import logging
import os
import tempfile

from app.appexport import repository as appexport_repo
from app.appexport.bundler import build_bundle_zip, build_standalone_bundle_zip
from app.appexport.freeze import freeze_config
from app.appexport.guard import check_export_guard
from app.appexport.snapshot import write_snapshot
from app.auth.dependency import is_appexport_enabled
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import request_scoped_session
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.jobs.common import notify_best_effort
from app.jobs.common import session_factory as _session_factory

logger = logging.getLogger(__name__)


def _notify(session_factory, *, tenant_id, item_id, user_id, status, error=None):
    """Écrit la notification in-app de fin d'export d'app — best-effort,
    jamais bloquant (cf. app.jobs.common.notify_best_effort). SP-43 Tâche 6 :
    ne garde ici que la résolution du titre de l'item propre au domaine
    appexport (`user_id` est déjà résolu par l'appelant, lu sur le job),
    elle-même protégée par son propre try/except best-effort."""
    try:
        with request_scoped_session(session_factory) as session:
            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
            title = item.title if item is not None else item_id
    except Exception:
        logger.exception("app export job : échec de la résolution du titre de notification")
        return
    notify_best_effort(
        session_factory,
        tenant_id=tenant_id,
        recipient_user_id=user_id,
        kind="appexport",
        status=status,
        item_id=item_id,
        item_resource_type="app",
        item_title=title,
        error=error,
    )


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _prepare_bundle_inputs(
    session,
    *,
    tenant_id: str,
    mode: str,
    config: BuilderConfig,
) -> tuple[BuilderConfig, dict | None]:
    if mode == "connected":
        core_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
        return config, {"coreUrl": core_url}
    return freeze_config(session, tenant_id=tenant_id, config=config), None


def _build_zip_bytes(session, *, tenant_id: str, mode: str, config: BuilderConfig) -> bytes:
    if mode == "standalone":
        with tempfile.TemporaryDirectory() as snapshot_dir:
            write_snapshot(session, tenant_id=tenant_id, config=config, snapshot_dir=snapshot_dir)
            return build_standalone_bundle_zip(config, snapshot_dir=snapshot_dir)
    bundle_config, connection = _prepare_bundle_inputs(
        session, tenant_id=tenant_id, mode=mode, config=config
    )
    runtime_dir = os.environ["APPEXPORT_RUNTIME_DIR"]
    return build_bundle_zip(bundle_config, runtime_dir=runtime_dir, connection=connection)


@app.task(queue="appexport")
def build_app_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_appexport_enabled():
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(
                session, job_id=job_id, error="app export capability disabled"
            )
        return

    # Toujours liés avant le premier bloc protégé : si get_job/mark_running
    # lève avant leur affectation réelle, le handler `except` plus bas doit
    # pouvoir les lire sans UnboundLocalError — même patron que
    # app.pipelines.jobs.run_pipeline_task/app.ingestion.tasks.run_ingestion_task
    # (GAP-56.1, SP-49 : ces deux appels étaient hors du bloc try ici, une
    # exception transitoire remontait alors non gérée — ni mark_error, ni
    # notification).
    item_id: str | None = None
    mode: str | None = None
    user_id: str | None = None

    try:
        with request_scoped_session(session_factory) as session:
            job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
            if job is None:
                logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
                return
            appexport_repo.mark_running(session, job_id=job_id)
            item_id = job.item_id
            mode = job.mode
            user_id = job.user_id

        with request_scoped_session(session_factory) as session:
            config_read = configs_repo.get_config_by_item(session, item_id)
            if config_read is None:
                raise ValueError(f"app export item '{item_id}' not found")
            guard_result = check_export_guard(
                session, tenant_id=tenant_id, config=config_read.config, mode=mode
            )
            if not guard_result.allowed:
                raise ValueError("; ".join(guard_result.reasons))
            zip_bytes = _build_zip_bytes(
                session, tenant_id=tenant_id, mode=mode, config=config_read.config
            )

        result_key = f"appexports/{job_id}.zip"
        bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        s3_client = s3_client_from_env()
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(
            Bucket=bucket, Key=result_key, Body=zip_bytes, ContentType="application/zip"
        )

        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
        _notify(
            session_factory, tenant_id=tenant_id, item_id=item_id, user_id=user_id, status="success"
        )
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("app export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
        _notify(
            session_factory,
            tenant_id=tenant_id,
            item_id=item_id,
            user_id=user_id,
            status="failure",
            error=str(exc),
        )


@app.periodic(cron="*/5 * * * *")
@app.task(queue="appexport")
def sweep_appexport_jobs_task(timestamp: int) -> None:
    """Réclame les appexport_jobs restés "running" (export-worker/process
    tué en cours de zip) : appexport_repo.reclaim_stuck_jobs existait déjà
    mais n'était appelée par aucune tâche périodique (GAP-56.2, SP-49).
    Cron aligné sur les 3 balayages */5 existants. Pas de notification :
    reclaim_stuck_jobs n'en a jamais prévu (même contrat côté export, câblé
    depuis SP-17b via le sweep de rapports — silencieux là aussi), rester
    symétrique par défaut est le choix le moins risqué."""
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        appexport_repo.reclaim_stuck_jobs(session)
        session.commit()
