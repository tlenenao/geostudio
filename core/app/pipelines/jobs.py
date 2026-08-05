# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-15a) : charge le Pipeline sauvegardé, l'exécute
via app.pipelines.runtime, met à jour le statut du run. Toute erreur marque
le run "failed", jamais de run bloqué en queued/running ("zombie", même
critère d'acceptation que SP-6a/run_ingestion_task). Tourne dans le worker
partagé (docker-compose.yml, queue dédiée "etl", cf. app.jobs pour la
raison de import_paths)."""
import logging
import os

from app.configs import repository as configs_repo
from app.configs.schemas import PipelinePayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.jobs import app
from app.pipelines import repository as pipelines_repo
from app.pipelines.runtime import PipelineRuntimeError, run_pipeline
from app.users.models import User

logger = logging.getLogger(__name__)


def _get_pipeline_payload(session, *, item_id: str) -> PipelinePayload:
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "pipeline":
        raise ValueError(f"pipeline item '{item_id}' not found")
    payload = config.config.pipeline
    assert payload is not None
    return payload


def _acting_user(session, *, tenant_id: str, item_id: str) -> User:
    # Le run s'exécute en arrière-plan, sans session HTTP authentifiée — on
    # ré-évalue les permissions (design §7 "double vérification") avec
    # l'identité du PROPRIÉTAIRE du pipeline, jamais un contournement admin
    # implicite : si le propriétaire a perdu l'accès à une collection depuis
    # la sauvegarde, le run échoue proprement (cf. _require_readable/
    # writable_collection dans app.pipelines.runtime). ItemRead (le type que
    # renvoie items_repo.get_item) ne porte pas owner_id (seulement
    # owner=username, cf. app.items.repository._to_read) — on le relit donc
    # directement sur le modèle ORM plutôt que de passer par ItemRead.
    from sqlalchemy import select

    from app.items.models import Item

    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise ValueError(f"pipeline item '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _s3_client_from_env():
    from app.ingestion.storage import make_s3_client

    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _analytics_base_uri() -> str:
    override = os.environ.get("S3_CDC_BUCKET_BASE_URI")  # test seam, local-disk fixtures
    if override:
        return override
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    return f"s3://{bucket}/cdc"


@app.task(queue="etl")
def run_pipeline_task(run_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)

    try:
        with request_scoped_session(session_factory) as session:
            run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
            if run is None:
                logger.error("pipeline run %s introuvable (tenant %s)", run_id, tenant_id)
                return
            pipelines_repo.mark_running(session, run_id=run_id)
            item_id = run.pipeline_item_id

        with request_scoped_session(session_factory) as session:
            payload = _get_pipeline_payload(session, item_id=item_id)
            user = _acting_user(session, tenant_id=tenant_id, item_id=item_id)
            stats = run_pipeline(
                session, payload=payload, tenant_id=tenant_id, user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
            )
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_succeeded(
                session, run_id=run_id,
                node_stats={s.nodeId: s.to_dict() for s in stats},
            )
    except (PipelineRuntimeError, ValueError) as exc:
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "failed", jamais zombie
        logger.exception("pipeline run %s : erreur inattendue", run_id)
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=f"erreur interne : {exc}")
