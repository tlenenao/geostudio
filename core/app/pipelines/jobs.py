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
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.audit.writer import write_audit
from app.auth.dependency import is_etl_enabled, is_read_only_mode
from app.configs import repository as configs_repo
from app.configs.pipeline_params import apply_params, resolve_params
from app.configs.schemas import PipelinePayload, PipelineRetryPolicy
from app.db import request_scoped_session
from app.items.models import Item
from app.jobs import app
from app.jobs.common import notify_best_effort, resolve_owner_user
from app.jobs.common import session_factory as _session_factory
from app.pipelines import checkpoints
from app.pipelines import repository as pipelines_repo
from app.pipelines.errors import PipelineCancelledError, PipelineTerminatedError
from app.pipelines.reader_state import ReaderState
from app.pipelines.runtime import NodeStat, PipelineRuntimeError, access_facts, run_pipeline
from app.quotas.service import QuotaExceededError
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


_MAX_RETRY_DELAY_S = 6 * 3600


def _flag_resumable(factory, run_id: str, root_id: str | None, tenant_id: str) -> None:
    """Échec définitif : signale à l'API (autre conteneur) que des points de
    reprise existent côté worker, pour proposer « Reprendre »."""
    if root_id is None:
        return
    try:
        if checkpoints.exists(tenant_id, root_id):
            with request_scoped_session(factory) as session:
                pipelines_repo.set_resumable(session, run_id=run_id, value=True)
    except Exception:
        logger.exception("pipeline run %s : drapeau resumable non posé", run_id)


def _clear_resumable(factory, root_ids: list[str]) -> None:
    try:
        with request_scoped_session(factory) as session:
            pipelines_repo.clear_resumable_for_roots(session, root_ids)
    except Exception:
        logger.exception("pipeline : drapeau resumable non retiré")


def _schedule_retry(
    factory,
    *,
    run_id: str,
    tenant_id: str,
    policy: PipelineRetryPolicy | None,
    attempt: int,
    error: str,
) -> bool:
    """F5 : si la politique `retry` le permet, passe le run en `retrying` et
    programme la reprise. Écriture validée AVANT defer (piège n°14) : un defer
    perdu est rattrapé par le balayage (`requeue_overdue_retries`)."""
    if policy is None or attempt > policy.max:
        return False
    delay = policy.delaySeconds * (2 ** (attempt - 1) if policy.backoff == "exponential" else 1)
    delay = min(delay, _MAX_RETRY_DELAY_S)
    try:
        with request_scoped_session(factory) as session:
            due = pipelines_repo.mark_retrying(
                session, run_id=run_id, error=error, delay_seconds=delay
            )
    except Exception:
        logger.exception("pipeline run %s : passage en reprise impossible", run_id)
        return False
    if due is None:  # annulé entre-temps : l'annulation suit son cours
        return False
    try:
        run_pipeline_task.configure(schedule_in={"seconds": delay}).defer(
            run_id=run_id, tenant_id=tenant_id
        )
    except Exception:
        logger.exception("pipeline run %s : defer de reprise perdu, le balayage reprendra", run_id)
    return True


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


class RunTracker(Protocol):
    """Seam introduit pour découpler run_pipeline_task de
    app.pipelines.repository (Postgres) — un futur sidecar desktop (design
    2026-09-17 §4, suivi de run en mémoire, sans Postgres) fournira sa
    propre implémentation sans dupliquer app.pipelines.runtime.run_pipeline."""

    def mark_running(self) -> bool:
        """True si le run a été pris en charge (queued -> running) ; False s'il
        n'est plus prenable (annulé, terminé, inconnu) : l'appelant ne doit
        alors rien exécuter (REV-275 c)."""
        ...

    def mark_succeeded(self, node_stats: dict) -> None: ...
    def mark_failed(self, error: str) -> None: ...
    def mark_cancelled(self) -> None: ...
    def is_cancel_requested(self) -> bool: ...


class PostgresRunTracker:
    """Implémentation par défaut, utilisée par le worker procrastinate —
    une transaction courte par transition de statut, comme l'ancien code
    inline (jamais une transaction partagée pour tout le run), sauf
    `mark_running` : celle-ci partageait auparavant la transaction de
    `get_run` (deux commits au lieu d'un après ce refactor, même état
    final en base, comportement observable inchangé)."""

    def __init__(
        self, session_factory: sessionmaker[Session], *, run_id: str, tenant_id: str
    ) -> None:
        self._session_factory = session_factory
        self._run_id = run_id
        # Non utilisé par les 3 méthodes ci-dessous (pipelines_repo.mark_*
        # filtre seulement par run_id, déjà le cas avant ce chantier, aucune
        # régression) : conservé comme contrat pressenti pour une future
        # implémentation en mémoire côté sidecar desktop, qui en aura
        # probablement besoin pour scoper son état — pas un filtre de
        # sécurité actif ici.
        self._tenant_id = tenant_id

    def mark_running(self) -> bool:
        with request_scoped_session(self._session_factory) as session:
            return pipelines_repo.mark_running(session, run_id=self._run_id)

    def mark_succeeded(self, node_stats: dict) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_succeeded(session, run_id=self._run_id, node_stats=node_stats)

    def mark_failed(self, error: str) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=self._run_id, error=error)

    def mark_cancelled(self) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_cancelled(session, run_id=self._run_id)

    def is_cancel_requested(self) -> bool:
        with request_scoped_session(self._session_factory) as session:
            return pipelines_repo.is_cancel_requested(session, run_id=self._run_id)


@app.task(queue="etl")
def run_pipeline_task(run_id: str, tenant_id: str) -> None:
    factory = _session_factory()
    tracker: RunTracker = PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)
    # Toujours lié avant le premier bloc protégé : si get_run/mark_running
    # lève avant l'affectation réelle (ci-dessous), les handlers `except`
    # doivent pouvoir le lire sans UnboundLocalError (même piège que
    # app.ingestion.tasks._notify, trouvé en revue de la Tâche 4, SP-39) —
    # None encode "item inconnu", donc pas de notification best-effort
    # possible dans ce cas (le statut du run est déjà marqué "failed" par
    # ailleurs, la garantie best-effort porte sur la notification, pas sur
    # le statut du run).
    item_id: str | None = None
    retry_policy: PipelineRetryPolicy | None = None
    attempt = 1
    root_id: str | None = None

    try:
        with request_scoped_session(factory) as session:
            run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
            if run is None:
                logger.error("pipeline run %s introuvable (tenant %s)", run_id, tenant_id)
                return
            if run.status == "cancelled":  # annulé avant sa prise en charge (t03b-009)
                return
            pipeline_item_id = run.pipeline_item_id
            run_params = dict(run.params or {})
            attempt = run.attempt
            # Racine des points de reprise : le run lui-même (reprise auto) ou le
            # run dont celui-ci reprend le travail (reprise manuelle).
            root_id = run.resume_of or run.id
        # `item_id` n'est affecté qu'APRÈS tracker.mark_running(), pas avant —
        # comme dans le code original où pipelines_repo.mark_running(...)
        # précédait `item_id = run.pipeline_item_id` dans le même bloc `with`.
        # Affecter `item_id` avant l'appel changerait un comportement
        # observable : si mark_running() lève, `item_id` resterait lié et les
        # handlers `except` écriraient une notification que le code original
        # n'écrivait jamais dans ce cas — régression couverte par
        # test_early_failure_before_item_id_bound_does_not_crash
        # (tests/test_pipeline_jobs.py), qui vérifie précisément l'absence de
        # cette notification.
        if not tracker.mark_running():  # annulé entre get_run et ici (REV-275 c) : rien à exécuter
            logger.info("pipeline run %s non démarré : plus en file (annulé entre-temps)", run_id)
            return
        item_id = pipeline_item_id

        with request_scoped_session(factory) as session:
            payload = _get_pipeline_payload(session, item_id=item_id)
            # Re-résolution idempotente : couvre les runs planifiés (cron, sans
            # params) qui retombent sur les défauts ; un paramètre requis sans
            # valeur échoue ici avec un message clair.
            payload = apply_params(payload, resolve_params(payload.parameters, run_params))
            user = _acting_user(session, tenant_id=tenant_id, item_id=item_id)
            retry_policy = payload.retry
            checkpoint = (
                checkpoints.Checkpoint(
                    tenant_id,
                    root_id,
                    checkpoints.config_fingerprint(
                        payload,
                        access_facts(session, payload, tenant_id=tenant_id, user=user),
                    ),
                )
                if retry_policy is not None
                else None
            )
            reader_state = ReaderState(
                pipelines_repo.get_reader_states(
                    session, tenant_id=tenant_id, pipeline_item_id=item_id
                )
            )
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
                on_node_complete=_make_progress_callback(
                    factory, run_id=run_id, tenant_id=tenant_id
                ),
                on_progress=_make_progress_callback(factory, run_id=run_id, tenant_id=tenant_id),
                should_cancel=tracker.is_cancel_requested,
                run_id=run_id,
                reader_state=reader_state,
                checkpoint=checkpoint,
            )
            # F4 : le curseur n'avance qu'ici, run réussi (jamais sur échec).
            if reader_state.pending:
                pipelines_repo.upsert_reader_states(
                    session,
                    tenant_id=tenant_id,
                    pipeline_item_id=item_id,
                    cursors=reader_state.pending,
                )
        checkpoints.discard(tenant_id, root_id)  # run réussi : plus rien à reprendre
        if checkpoint is not None:
            _clear_resumable(factory, [root_id])
        tracker.mark_succeeded({s.nodeId: s.to_dict() for s in stats})
        assert item_id is not None  # affecté ci-dessus, jamais atteint sinon (cf. return/raise)
        _notify(factory, tenant_id=tenant_id, item_id=item_id, status="success")
    except PipelineCancelledError:
        tracker.mark_cancelled()
    # REV-288a : un quota atteint est un refus métier (message destiné à
    # l'utilisateur), même traitement que l'ingestion (ingestion/tasks.py).
    except (PipelineRuntimeError, ValueError, QuotaExceededError) as exc:
        if (
            isinstance(exc, PipelineRuntimeError)
            and not isinstance(exc, PipelineTerminatedError)
            and _schedule_retry(
                factory,
                run_id=run_id,
                tenant_id=tenant_id,
                policy=retry_policy,
                attempt=attempt,
                error=str(exc),
            )
        ):
            return
        tracker.mark_failed(str(exc))
        _flag_resumable(factory, run_id, root_id, tenant_id)
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
        if _schedule_retry(
            factory,
            run_id=run_id,
            tenant_id=tenant_id,
            policy=retry_policy,
            attempt=attempt,
            error=f"erreur interne : {exc}",
        ):
            return
        tracker.mark_failed(f"erreur interne : {exc}")
        _flag_resumable(factory, run_id, root_id, tenant_id)
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
@app.task(queue="etl", queueing_lock="run_pipeline_sweep_task")
def run_pipeline_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de planification de pipelines ignoré")
        return
    if not is_etl_enabled():
        return
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        # F5 : reprises dont le defer a été perdu (piège n°14), puis purge des
        # points de reprise expirés (best-effort, disque local du worker).
        overdue = pipelines_repo.requeue_overdue_retries(session)
        session.commit()
        for overdue_run_id, overdue_tenant_id in overdue:
            run_pipeline_task.defer(run_id=overdue_run_id, tenant_id=overdue_tenant_id)
        try:
            expired = checkpoints.purge_expired()
            if expired:  # plus de points de reprise : ne plus proposer « Reprendre »
                pipelines_repo.clear_resumable_for_roots(session, [r for _, r in expired])
                session.commit()
        except Exception:
            logger.exception("purge des points de reprise échouée")
        pipelines_repo.reclaim_stuck_runs(session)
        session.commit()  # sinon le rollback d'un PipelineRunActive annule la reprise
        due = pipelines_repo.list_due_pipelines(session)
        for item_id, tenant_id in due:
            try:
                run = pipelines_repo.create_run_unless_active(
                    session, tenant_id=tenant_id, pipeline_item_id=item_id
                )
            except pipelines_repo.PipelineRunActive:
                # REV-310 : un run (ex. déclenchement manuel) est apparu depuis le
                # calcul « dû » ; le prochain balayage re-décidera.
                session.rollback()
                continue
            # c03-003 : même trace que run_pipeline_service ; acteur = propriétaire
            # (identité sous laquelle le run s'exécutera), actor_kind="schedule".
            owner = session.get(Item, item_id)
            write_audit(
                session,
                tenant_id=tenant_id,
                actor_id=owner.owner_id if owner else None,
                actor_kind="schedule",
                action="pipeline.run",
                object_type="pipeline_run",
                object_id=run.id,
                payload={"pipelineItemId": item_id},
            )
            # Commit avant de déférer, même raison que routes.py/mcp/tools.py
            # (create_run puis defer) : un worker pourrait ramasser la tâche
            # avant que la ligne pipeline_runs ne soit visible autrement. À
            # l'intérieur de la boucle car chaque run doit être visible avant
            # SON propre defer, pas seulement le dernier de la file.
            session.commit()
            run_pipeline_task.defer(run_id=run.id, tenant_id=tenant_id)
