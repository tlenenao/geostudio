# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-15a) : charge le Pipeline sauvegardé, l'exécute
via app.pipelines.runtime, met à jour le statut du run. Toute erreur marque
le run "failed", jamais de run bloqué en queued/running ("zombie", même
critère d'acceptation que SP-6a/run_ingestion_task). Tourne dans le worker
partagé (docker-compose.yml, queue dédiée "etl", cf. app.jobs pour la
raison de import_paths)."""

import logging
import os
from collections.abc import Callable

from app.auth.dependency import is_etl_enabled, is_read_only_mode
from app.configs import repository as configs_repo
from app.configs.schemas import PipelinePayload
from app.db import request_scoped_session
from app.jobs import app
from app.jobs.common import notify_best_effort, resolve_owner_user
from app.jobs.common import session_factory as _session_factory
from app.pipelines import repository as pipelines_repo
from app.pipelines.runtime import NodeStat, PipelineRuntimeError, run_pipeline
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
    # writable_collection dans app.pipelines.runtime).
    #
    # SP-43 Tâche 6 : corps migré vers app.jobs.common.resolve_owner_user
    # (identique) ; ce thin wrapper reconvertit son LookupError générique en
    # ValueError, pour ne changer aucun comportement observable des
    # appelants existants (run_pipeline_task attrape (PipelineRuntimeError,
    # ValueError) explicitement).
    try:
        return resolve_owner_user(session, tenant_id=tenant_id, item_id=item_id)
    except LookupError as exc:
        raise ValueError(str(exc)) from exc


def _owner_and_title(session, *, tenant_id: str, item_id: str) -> tuple[str, str]:
    from sqlalchemy import select

    from app.items.models import Item

    row = session.execute(
        select(Item.owner_id, Item.title).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).one()
    return row.owner_id, row.title


def _notify(
    session_factory,
    *,
    tenant_id: str,
    item_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Écrit la notification in-app de fin de run — best-effort, jamais
    bloquant : son propre bloc try/except, séparé de celui qui commite
    mark_succeeded/mark_failed, pour qu'un échec ici ne fasse jamais
    rollback d'un changement de statut de run déjà réussi (même patron que
    app.ingestion.tasks._notify, SP-39/Tâche 4).

    SP-43 Tâche 6 : l'écriture proprement dite (session isolée, commit,
    avaler toute exception) est désormais déléguée à
    app.jobs.common.notify_best_effort — cette fonction ne garde que la
    résolution owner+titre propre au domaine pipeline (_owner_and_title),
    elle-même protégée par son propre try/except best-effort."""
    try:
        with request_scoped_session(session_factory) as session:
            owner_id, title = _owner_and_title(session, tenant_id=tenant_id, item_id=item_id)
    except Exception:
        logger.exception("pipeline run : échec de la résolution du destinataire de notification")
        return
    notify_best_effort(
        session_factory,
        tenant_id=tenant_id,
        recipient_user_id=owner_id,
        kind="pipeline",
        status=status,
        item_id=item_id,
        item_resource_type="pipeline",
        item_title=title,
        error=error,
    )


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


def _make_progress_callback(
    session_factory,
    *,
    run_id: str,
    tenant_id: str,
) -> Callable[[NodeStat], None]:
    def _on_node_complete(stat: NodeStat) -> None:
        with request_scoped_session(session_factory) as s:
            pipelines_repo.append_node_stat(
                s,
                tenant_id=tenant_id,
                run_id=run_id,
                node_id=stat.nodeId,
                stat=stat.to_dict(),
            )

    return _on_node_complete


@app.task(queue="etl")
def run_pipeline_task(run_id: str, tenant_id: str) -> None:
    factory = _session_factory()
    # Toujours lié avant le premier bloc protégé : si get_run/mark_running
    # lève avant l'affectation réelle (ci-dessous), les handlers `except`
    # doivent pouvoir le lire sans UnboundLocalError (même piège que
    # app.ingestion.tasks._notify, trouvé en revue de la Tâche 4, SP-39) —
    # None encode "item inconnu", donc pas de notification best-effort
    # possible dans ce cas (le statut du run est déjà marqué "failed" par
    # ailleurs, la garantie best-effort porte sur la notification, pas sur
    # le statut du run).
    item_id: str | None = None

    try:
        with request_scoped_session(factory) as session:
            run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
            if run is None:
                logger.error("pipeline run %s introuvable (tenant %s)", run_id, tenant_id)
                return
            pipelines_repo.mark_running(session, run_id=run_id)
            item_id = run.pipeline_item_id

        with request_scoped_session(factory) as session:
            payload = _get_pipeline_payload(session, item_id=item_id)
            user = _acting_user(session, tenant_id=tenant_id, item_id=item_id)
            stats = run_pipeline(
                session,
                payload=payload,
                tenant_id=tenant_id,
                user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"],
                secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
                qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
                qgis_worker_timeout_seconds=int(
                    os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")
                ),
                on_node_complete=_make_progress_callback(
                    factory, run_id=run_id, tenant_id=tenant_id
                ),
            )
        with request_scoped_session(factory) as session:
            pipelines_repo.mark_succeeded(
                session,
                run_id=run_id,
                node_stats={s.nodeId: s.to_dict() for s in stats},
            )
        assert item_id is not None  # affecté ci-dessus, jamais atteint sinon (cf. return/raise)
        _notify(factory, tenant_id=tenant_id, item_id=item_id, status="success")
    except (PipelineRuntimeError, ValueError) as exc:
        with request_scoped_session(factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=str(exc))
        if item_id is not None:
            _notify(
                factory,
                tenant_id=tenant_id,
                item_id=item_id,
                status="failure",
                error=str(exc),
            )
        else:
            logger.info("pipeline run %s : notification ignorée (item inconnu)", run_id)
    except Exception as exc:  # toute erreur inattendue finit "failed", jamais zombie
        logger.exception("pipeline run %s : erreur inattendue", run_id)
        with request_scoped_session(factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=f"erreur interne : {exc}")
        if item_id is not None:
            _notify(
                factory,
                tenant_id=tenant_id,
                item_id=item_id,
                status="failure",
                error=f"erreur interne : {exc}",
            )
        else:
            logger.info("pipeline run %s : notification ignorée (item inconnu)", run_id)


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def run_pipeline_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de planification de pipelines ignoré")
        return
    if not is_etl_enabled():
        return
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        due = pipelines_repo.list_due_pipelines(session)
        for item_id, tenant_id in due:
            run = pipelines_repo.create_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)
            # Commit avant de déférer, même raison que routes.py/mcp/tools.py
            # (create_run puis defer) : un worker pourrait ramasser la tâche
            # avant que la ligne pipeline_runs ne soit visible autrement. À
            # l'intérieur de la boucle car chaque run doit être visible avant
            # SON propre defer, pas seulement le dernier de la file.
            session.commit()
            run_pipeline_task.defer(run_id=run.id, tenant_id=tenant_id)
