# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import croniter
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session, aliased

from app.audit.models import AuditLog
from app.configs import repository as configs_repo
from app.configs.models import Config, ConfigRevision
from app.items.models import Item
from app.outbox.emit import emit
from app.pipelines.models import PipelineReaderState, PipelineRun, PipelineWebhookToken
from app.quotas.service import max_active_runs_per_tenant, quotas_enabled
from app.users.models import User

# AUD-084 : N échecs consécutifs ouvrent le circuit (plus de run planifié).
CIRCUIT_BREAKER_FAILURES = 3


def _now() -> datetime:
    return datetime.now(UTC)


_RUNNING_RECLAIM_MINUTES = 60


def create_run(
    session: Session,
    *,
    tenant_id: str,
    pipeline_item_id: str,
    params: dict | None = None,
    resume_of: str | None = None,
    node_stats: dict | None = None,
    idempotency_key: str | None = None,
) -> PipelineRun:
    run = PipelineRun(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        pipeline_item_id=pipeline_item_id,
        status="queued",
        params=params or None,
        resume_of=resume_of,
        node_stats=node_stats or {},
        idempotency_key=idempotency_key,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


class PipelineRunActive(Exception):
    """Un run non périmé (queued/running/cancel_requested) existe déjà (REV-310)."""


_ACTIVE_STATUSES = ("queued", "pending", "running", "cancel_requested", "retrying")


def _run_anchor():
    """Horloge de péremption d'un run : `started_at` une fois démarré, sinon
    `created_at` (même règle que reclaim_stuck_runs)."""
    return func.coalesce(
        case(
            (
                PipelineRun.status.in_(("running", "cancel_requested")),
                func.coalesce(PipelineRun.heartbeat_at, PipelineRun.started_at),
            ),
            (PipelineRun.status == "retrying", PipelineRun.next_retry_at),
            else_=PipelineRun.created_at,
        ),
        PipelineRun.created_at,
    )


def create_run_unless_active(
    session: Session,
    *,
    tenant_id: str,
    pipeline_item_id: str,
    stale_minutes: int = _RUNNING_RECLAIM_MINUTES,
    params: dict | None = None,
    resume_of: str | None = None,
    node_stats: dict | None = None,
    idempotency_key: str | None = None,
) -> PipelineRun:
    """REV-310 : crée un run SAUF si un run actif non périmé existe (lève
    PipelineRunActive). Point unique REST / MCP / webhook / cron. Atomique :
    sous Postgres, un verrou advisory de transaction par pipeline sérialise
    « vérifier puis insérer » jusqu'au commit de l'appelant (un SELECT puis
    INSERT nu laisserait passer deux requêtes simultanées). Un run périmé
    (plus vieux que le seuil de reprise) est ignoré, comme reclaim_stuck_runs.
    # ponytail: SQLite (tests) sans verrou — mono-connexion, pas de concurrence réelle."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(pipeline_item_id, 0)))
        )
    threshold = _now() - timedelta(minutes=stale_minutes)
    active = session.execute(
        select(PipelineRun.id)
        .where(
            PipelineRun.tenant_id == tenant_id,
            PipelineRun.pipeline_item_id == pipeline_item_id,
            PipelineRun.status.in_(_ACTIVE_STATUSES),
            _run_anchor() >= threshold,
        )
        .limit(1)
    ).first()
    if active is not None:
        raise PipelineRunActive(pipeline_item_id)
    # AUD-098 : plafond de runs actifs par tenant (REST/MCP/webhook : 409 ; cron : reporté
    # au balayage suivant, comme un run déjà actif).
    cap = max_active_runs_per_tenant(session, tenant_id) if quotas_enabled() else None
    if cap is not None:
        running = session.scalar(
            select(func.count())
            .select_from(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant_id,
                PipelineRun.status.in_(_ACTIVE_STATUSES),
                _run_anchor() >= threshold,
            )
        )
        if (running or 0) >= cap:
            raise PipelineRunActive(f"tenant run cap {cap} reached")
    return create_run(
        session,
        tenant_id=tenant_id,
        pipeline_item_id=pipeline_item_id,
        params=params,
        resume_of=resume_of,
        node_stats=node_stats,
        idempotency_key=idempotency_key,
    )


def find_run_by_idempotency_key(
    session: Session, *, tenant_id: str, pipeline_item_id: str, key: str
) -> str | None:
    return session.scalar(
        select(PipelineRun.id).where(
            PipelineRun.tenant_id == tenant_id,
            PipelineRun.pipeline_item_id == pipeline_item_id,
            PipelineRun.idempotency_key == key,
        )
    )


def get_run(session: Session, *, tenant_id: str, run_id: str) -> PipelineRun | None:
    return session.execute(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.tenant_id == tenant_id)
    ).scalar_one_or_none()


def list_runs(
    session: Session,
    *,
    tenant_id: str,
    pipeline_item_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[PipelineRun]:
    rows = (
        session.execute(
            select(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id
            )
            .order_by(PipelineRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows)


def get_latest_run(
    session: Session, *, tenant_id: str, pipeline_item_id: str
) -> PipelineRun | None:
    return (
        session.execute(
            select(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id
            )
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_latest_runs_for_items(session: Session, *, item_ids: list[str]) -> dict[str, PipelineRun]:
    """Batch de get_latest_run pour une liste d'item_id — remplace l'appel
    par itération de list_due_pipelines (GAP-64, SP-49) : une seule requête
    au lieu de N. tenant_id n'est volontairement pas un paramètre de filtre
    ici (contrairement à get_latest_run) : les item_id proviennent déjà de
    list_configs_by_kind (cross-tenant par nature pour ce balayage
    système)."""
    if not item_ids:
        return {}
    rn = (
        func.row_number()
        .over(
            partition_by=PipelineRun.pipeline_item_id,
            order_by=PipelineRun.created_at.desc(),
        )
        .label("rn")
    )
    subq = select(PipelineRun, rn).where(PipelineRun.pipeline_item_id.in_(item_ids)).subquery()
    pr = aliased(PipelineRun, subq)
    rows = session.execute(select(pr).where(subq.c.rn == 1)).scalars().all()
    return {r.pipeline_item_id: r for r in rows}


def mark_running(session: Session, *, run_id: str) -> bool:
    """REV-275 (c) : transition conditionnelle `queued|pending -> running`
    (UPDATE ... WHERE status IN ...). Retourne False si le run n'est plus
    prenable — annulé entre-temps par `request_cancel`, déjà terminé, réclamé
    par `reclaim_stuck_runs`, ou inconnu : l'appelant sort alors sans
    exécuter. Remplace l'ancien écrasement inconditionnel (un `cancelled`
    repassait `running`)."""
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run_id, PipelineRun.status.in_(("queued", "pending", "retrying")))
        .values(
            status="running",
            started_at=_now(),
            heartbeat_at=None,  # AUD-026 : pas de battement périmé d'une tentative précédente
            finished_at=None,
            error=None,
            next_retry_at=None,
        )
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def request_cancel(session: Session, run: PipelineRun) -> str:
    """t03b-009 : un run « queued » passe directement à « cancelled » (la tâche
    le verra et ne l'exécutera pas) ; un run « running » passe à
    « cancel_requested », testé par l'écrivain entre deux lots."""

    # REV-275 (c) : UPDATE conditionnels — l'instantané ORM peut être périmé
    # (le worker a pu passer queued -> running entre la lecture et ici).
    def _transition(src: str, **values: object) -> bool:
        res = session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run.id, PipelineRun.status == src)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return bool(res.rowcount)  # type: ignore[attr-defined]

    terminal = _transition("queued", status="cancelled", finished_at=_now()) or _transition(
        "retrying", status="cancelled", finished_at=_now(), next_retry_at=None
    )
    if not terminal:
        _transition("running", status="cancel_requested")
    session.flush()
    session.refresh(run)
    if terminal:
        # F6 : clôture directe (queued/retrying -> cancelled) = fin de run, comme mark_cancelled.
        _emit_run_finished(session, run)
    return run.status


def is_cancel_requested(session: Session, *, run_id: str) -> bool:
    run = session.get(PipelineRun, run_id)
    return run is not None and run.status == "cancel_requested"


def mark_cancelled(session: Session, *, run_id: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    previous = _stored_status(session, run_id)
    run.status = "cancelled"
    run.finished_at = _now()
    session.flush()
    _emit_run_finished(session, run, previous=previous)


def _stored_status(session: Session, run_id: str) -> str | None:
    # Statut en base (pas l'instance ORM, possiblement périmée : un reclaim a pu le
    # clore depuis un autre processus).
    return session.scalar(select(PipelineRun.status).where(PipelineRun.id == run_id))


def _emit_run_finished(session: Session, run: PipelineRun, *, previous: str | None = None) -> None:
    # F6 (ADR 0027) : dans la transaction qui clôt le run — seulement sur un VRAI
    # changement de statut (reclaim -> failed puis worker -> failed : un seul
    # événement ; une fin réelle qui corrige un reclaim, elle, est émise).
    if previous == run.status:
        return
    emit(
        session,
        tenant_id=run.tenant_id,
        event_type="pipeline.run.finished",
        payload={"pipelineItemId": run.pipeline_item_id, "runId": run.id, "status": run.status},
    )


def mark_succeeded(session: Session, *, run_id: str, node_stats: dict) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    # F2 : un run qui a écarté des lignes vers la quarantaine n'est pas un succès net.
    rejected = any((s or {}).get("rejected") for s in node_stats.values())
    previous = _stored_status(session, run_id)
    run.status = "succeeded_with_rejects" if rejected else "succeeded"
    run.error = None  # run vivant clos à tort par reclaim_stuck_runs : la fin réelle prime
    run.finished_at = _now()
    run.node_stats = node_stats
    session.flush()
    _emit_run_finished(session, run, previous=previous)


def mark_failed(
    session: Session, *, run_id: str, error: str, failed_node_id: str | None = None
) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    previous = _stored_status(session, run_id)
    run.status = "failed"
    run.finished_at = _now()
    run.error = error
    run.failed_node_id = failed_node_id
    session.flush()
    _emit_run_finished(session, run, previous=previous)


def mark_failed_if_queued(session: Session, *, run_id: str, error: str) -> bool:
    """Transition conditionnelle `queued|pending -> failed` (UPDATE ... WHERE statut) :
    un run qu'un worker a déjà pris (`running`) n'est jamais écrasé (AUD-025)."""
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run_id, PipelineRun.status.in_(("queued", "pending")))
        .values(status="failed", finished_at=_now(), error=error)
    )
    session.flush()
    if not result.rowcount:  # type: ignore[attr-defined]
        return False
    run = session.get(PipelineRun, run_id)
    assert run is not None
    session.refresh(run)
    _emit_run_finished(session, run, previous="queued")
    return True


def mark_retrying(
    session: Session, *, run_id: str, error: str, delay_seconds: int
) -> datetime | None:
    """F5 : `running -> retrying` (UPDATE conditionnel : un run annulé entre-temps
    n'est pas relancé), attempt+1, échéance posée. Retourne l'échéance, ou None
    si le run n'était plus `running`."""
    due = _now() + timedelta(seconds=delay_seconds)
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run_id, PipelineRun.status == "running")
        .values(
            status="retrying",
            attempt=PipelineRun.attempt + 1,
            next_retry_at=due,
            error=error,
            finished_at=None,
        )
    )
    session.flush()
    return due if result.rowcount else None  # type: ignore[attr-defined]


def set_resumable(session: Session, *, run_id: str, value: bool) -> None:
    session.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(resumable=value))
    session.flush()


def clear_resumable_for_roots(session: Session, root_ids: list[str]) -> None:
    """Points de reprise supprimés (expirés / run réussi) : retire `resumable` du run
    racine et des runs qui le reprennent."""
    if not root_ids:
        return
    session.execute(
        update(PipelineRun)
        .where(PipelineRun.resumable.is_(True))
        .where((PipelineRun.id.in_(root_ids)) | (PipelineRun.resume_of.in_(root_ids)))
        .values(resumable=False)
    )
    session.flush()


def requeue_overdue_retries(
    session: Session, *, grace_seconds: int = 120, now: datetime | None = None
) -> list[tuple[str, str]]:
    """Runs `retrying` dont l'échéance est dépassée de plus de `grace_seconds`
    (defer perdu — piège n°14) : repousse l'échéance (la grâce repart) et
    retourne (run_id, tenant_id) à re-déférer. `mark_running` conditionnel rend
    un doublon de défer inoffensif. Cross-tenant, appelée par le balayage cron."""
    now = now or _now()
    rows = session.execute(
        select(PipelineRun.id, PipelineRun.tenant_id).where(
            PipelineRun.status == "retrying",
            PipelineRun.next_retry_at < now - timedelta(seconds=grace_seconds),
        )
    ).all()
    if rows:
        session.execute(
            update(PipelineRun)
            .where(PipelineRun.id.in_([r[0] for r in rows]), PipelineRun.status == "retrying")
            .values(next_retry_at=now)
        )
        session.flush()
    return [(r[0], r[1]) for r in rows]


def touch_heartbeat(session: Session, *, run_id: str) -> None:
    session.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run_id, PipelineRun.status.in_(("running", "cancel_requested")))
        .values(heartbeat_at=_now())
    )


def reclaim_stuck_runs(
    session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES
) -> int:
    """Clôt en erreur les runs « queued » (jamais pris en charge : defer perdu,
    file non consommée — P01.04) ou « running » (ancrés sur started_at —
    c02-005 : sans cela l'ancien run restait zombie à côté du nouveau) plus
    vieux que le seuil. Cross-tenant, appelée par le balayage cron. UPDATE
    conditionnel sur le statut : un run terminé entre-temps n'est pas touché.
    # AUD-026 : un run `running` est ancré sur son dernier battement de cœur
    # (`heartbeat_at`, thread du worker) ; sans battement, sur `started_at`.
    # ponytail: seuil = worker mort ; un worker gelé mais battant n'est pas clos."""
    threshold = _now() - timedelta(minutes=older_than_minutes)
    anchor = case(
        (
            PipelineRun.status.in_(("running", "cancel_requested")),
            func.coalesce(PipelineRun.heartbeat_at, PipelineRun.started_at),
        ),
        (PipelineRun.status == "retrying", PipelineRun.next_retry_at),
        else_=PipelineRun.created_at,
    )
    runs = session.scalars(
        select(PipelineRun)
        .where(
            PipelineRun.status.in_(("queued", "running", "cancel_requested", "retrying")),
            func.coalesce(anchor, PipelineRun.created_at) < threshold,
        )
        # verrou de ligne : un run qui se termine pendant le balayage n'est pas écrasé
        # (skip_locked : sans effet sous sqlite, effectif sous Postgres)
        .with_for_update(skip_locked=True)
    ).all()
    for run in runs:
        run.status = "failed"
        run.finished_at = _now()
        run.error = "run périmé : jamais terminé, clos par le balayage de planification"
        session.flush()
        _emit_run_finished(session, run)  # F6 : une fois par run touché, même transaction
    return len(runs)


def append_node_stat(
    session: Session, *, tenant_id: str, run_id: str, node_id: str, stat: dict
) -> None:
    """Écrit un NodeStat dans PipelineRun.node_stats immédiatement (fusion,
    pas un remplacement) — c'est ce qui permet à la progression d'un run
    d'être visible en base avant sa fin (SP-15g §3.5). Scindé de
    mark_succeeded (qui réécrit node_stats en entier, idempotent) : cette
    fonction est appelée une fois PAR NŒUD, sur sa propre transaction courte
    (jobs.py::_make_progress_callback), jamais dans la même transaction que
    le reste du run."""
    run = session.execute(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if run is None:
        return
    run.node_stats = {**run.node_stats, node_id: stat}
    session.flush()


def _config_anchor_by_item(session: Session, item_ids: list[str]) -> dict[str, datetime]:
    """Date d'écriture de la révision courante de la config de chaque pipeline."""
    if not item_ids:
        return {}
    rows = session.execute(
        select(Config.item_id, ConfigRevision.created_at)
        .join(
            ConfigRevision,
            (ConfigRevision.config_id == Config.id)
            & (ConfigRevision.version == Config.current_version),
        )
        .where(Config.item_id.in_(item_ids))
    ).all()
    return {item_id: created_at for item_id, created_at in rows}


def list_due_pipelines(session: Session, *, now: datetime | None = None) -> list[tuple[str, str]]:
    """Balayage cross-tenant des pipelines planifiés dus, consommé par
    run_pipeline_sweep_task (app.pipelines.jobs, SP-15h). "Dernier run"
    dérivé de pipeline_runs (jamais une colonne dupliquée) ; garde de
    concurrence par âge identique à app.harvest.repository.list_due_sources
    (_RUNNING_RECLAIM_MINUTES) — un run resté "running"/"queued" plus vieux
    que ce délai est présumé planté et redevient éligible."""
    now = now or datetime.now(UTC)
    due: list[tuple[str, str]] = []
    candidates = [
        (item_id, tenant_id, config)
        for item_id, tenant_id, config in configs_repo.list_configs_by_kind(
            session, kind="pipeline", refresh_enabled_only=True
        )
        if config.pipeline is not None
        and config.pipeline.refreshPolicy is not None
        and config.pipeline.refreshPolicy.enabled
    ]
    if candidates:
        # AUD-084 : un propriétaire anonymisé (RGPD) ne fait plus tourner de run planifié.
        erased = set(
            session.scalars(
                select(Item.id)
                .join(User, User.id == Item.owner_id)
                .where(Item.id.in_([c[0] for c in candidates]), User.erased_at.is_not(None))
            )
        )
        candidates = [c for c in candidates if c[0] not in erased]
    recent_by_item = _recent_terminal_statuses(session, [c[0] for c in candidates])
    latest_by_item = get_latest_runs_for_items(session, item_ids=[c[0] for c in candidates])
    # REV-312 : sans run antérieur, le curseur est la création/activation de la
    # config (révision courante) — un cron annuel n'est pas dû au 1er balayage.
    config_anchor = _config_anchor_by_item(session, [c[0] for c in candidates])
    for item_id, tenant_id, config in candidates:
        payload = config.pipeline
        policy = payload.refreshPolicy
        tz = ZoneInfo(policy.timezone)
        if _circuit_open(recent_by_item.get(item_id, [])):
            # AUD-084 : circuit ouvert — plus de run planifié tant qu'un run manuel n'a pas
            # réussi (le propriétaire est notifié à chaque échec, pas à chaque tick).
            continue
        latest = latest_by_item.get(item_id)
        if latest is None:
            anchor = config_anchor.get(item_id)
            if anchor is not None:
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=UTC)
                if croniter.croniter(policy.cron, anchor.astimezone(tz)).get_next(datetime) > now:
                    continue
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if latest.status in ("queued", "running", "cancel_requested", "retrying"):
            # Ancre de péremption : pour un run "running", l'horloge pertinente
            # est started_at (posé par mark_running), pas created_at (heure de
            # mise en file) — sinon un run resté longtemps en file d'attente
            # avant de démarrer réellement est réclamé comme planté dès le
            # tick suivant son passage à "running", alors qu'il vient tout
            # juste de commencer à progresser. Pour "queued", pas d'autre
            # ancre disponible avant que le run démarre : created_at reste
            # correct.
            reclaim_anchor = created_at
            if latest.status != "queued" and latest.started_at is not None:
                reclaim_anchor = latest.started_at
                if reclaim_anchor.tzinfo is None:
                    reclaim_anchor = reclaim_anchor.replace(tzinfo=UTC)
            if (now - reclaim_anchor) < timedelta(minutes=_RUNNING_RECLAIM_MINUTES):
                continue
            due.append((item_id, tenant_id))
            continue
        next_tick = croniter.croniter(policy.cron, created_at.astimezone(tz)).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due


def previous_run_failed(session: Session, *, item_id: str, run_id: str) -> bool:
    """Le dernier run terminé (succès ou échec) avant `run_id` a-t-il échoué ?"""
    prev = session.scalar(
        select(PipelineRun.status)
        .where(
            PipelineRun.pipeline_item_id == item_id,
            PipelineRun.id != run_id,
            PipelineRun.status.in_(("succeeded", "succeeded_with_rejects", "failed")),
        )
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    )
    return prev == "failed"


def is_scheduled_run(session: Session, *, tenant_id: str, run_id: str) -> bool:
    """Run créé par le balayage cron (trace `actor_kind="schedule"` écrite juste après
    sa création, cf. jobs.sweep). Borné dans le temps pour rester sur l'index
    (tenant_id, created_at) d'audit_log."""
    run = session.get(PipelineRun, run_id)
    if run is None:
        return False
    return (
        session.scalar(
            select(AuditLog.id)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.created_at >= run.created_at - timedelta(seconds=1),
                AuditLog.object_type == "pipeline_run",
                AuditLog.object_id == run_id,
                AuditLog.actor_kind == "schedule",
            )
            .limit(1)
        )
        is not None
    )


def _circuit_open(recent: list[str]) -> bool:
    return len(recent) == CIRCUIT_BREAKER_FAILURES and all(s == "failed" for s in recent)


def schedule_suspended(session: Session, *, item_id: str) -> bool:
    """AUD-084 (revue L5 I7) : planification suspendue par le coupe-circuit."""
    return _circuit_open(_recent_terminal_statuses(session, [item_id]).get(item_id, []))


def circuit_just_opened(session: Session, *, item_id: str) -> bool:
    """Le dernier échec vient d'ouvrir le circuit (N échecs, le N+1e terminal n'en est pas
    un) — pour notifier une seule fois, pas à chaque échec suivant."""
    recent = _recent_terminal_statuses(session, [item_id], CIRCUIT_BREAKER_FAILURES + 1).get(
        item_id, []
    )
    return _circuit_open(recent[:CIRCUIT_BREAKER_FAILURES]) and (
        len(recent) == CIRCUIT_BREAKER_FAILURES or recent[-1] != "failed"
    )


def _recent_terminal_statuses(
    session: Session, item_ids: list[str], n: int = CIRCUIT_BREAKER_FAILURES
) -> dict[str, list[str]]:
    """Les CIRCUIT_BREAKER_FAILURES derniers statuts terminaux par pipeline (du plus récent).
    Un run annulé n'est ni un succès ni un échec : il ne remet pas le compteur à zéro."""
    if not item_ids:
        return {}
    rn = (
        func.row_number()
        .over(partition_by=PipelineRun.pipeline_item_id, order_by=PipelineRun.created_at.desc())
        .label("rn")
    )
    sub = (
        select(PipelineRun.pipeline_item_id, PipelineRun.status, rn)
        .where(
            PipelineRun.pipeline_item_id.in_(item_ids),
            PipelineRun.status.in_(("succeeded", "succeeded_with_rejects", "failed")),
        )
        .subquery()
    )
    out: dict[str, list[str]] = {}
    for item_id, status in session.execute(
        select(sub.c.pipeline_item_id, sub.c.status)
        .where(sub.c.rn <= n)
        .order_by(sub.c.pipeline_item_id, sub.c.rn)
    ):
        out.setdefault(item_id, []).append(status)
    return out


# --- PipelineWebhookToken (GAP-24, SP-53) ---


def create_webhook_token(
    session: Session, *, tenant_id: str, pipeline_item_id: str, token_hash: str, created_by: str
) -> PipelineWebhookToken:
    token = PipelineWebhookToken(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        pipeline_item_id=pipeline_item_id,
        token_hash=token_hash,
        created_by=created_by,
    )
    session.add(token)
    session.flush()
    session.refresh(token)
    return token


def get_webhook_token(
    session: Session, *, tenant_id: str, token_id: str
) -> PipelineWebhookToken | None:
    return session.execute(
        select(PipelineWebhookToken).where(
            PipelineWebhookToken.id == token_id, PipelineWebhookToken.tenant_id == tenant_id
        )
    ).scalar_one_or_none()


def get_webhook_token_by_hash(session: Session, *, token_hash: str) -> PipelineWebhookToken | None:
    # Cross-tenant par construction : au moment du déclenchement, un
    # appelant externe ne connaît que le jeton, jamais le tenant à
    # l'avance (index unique sur token_hash seul, migration 0035).
    return session.execute(
        select(PipelineWebhookToken).where(PipelineWebhookToken.token_hash == token_hash)
    ).scalar_one_or_none()


def delete_webhook_token(session: Session, token: PipelineWebhookToken) -> None:
    session.delete(token)
    session.flush()


def touch_webhook_token(session: Session, token: PipelineWebhookToken) -> None:
    token.last_used_at = _now()
    session.flush()


def list_webhook_tokens_for_pipeline(
    session: Session, *, tenant_id: str, pipeline_item_id: str
) -> list[PipelineWebhookToken]:
    rows = (
        session.execute(
            select(PipelineWebhookToken)
            .where(
                PipelineWebhookToken.tenant_id == tenant_id,
                PipelineWebhookToken.pipeline_item_id == pipeline_item_id,
            )
            .order_by(PipelineWebhookToken.created_at.desc())
        )
        .scalars()
        .all()
    )
    return list(rows)


# --- PipelineReaderState (ARC-K2/F4) ---


def get_reader_states(session: Session, *, tenant_id: str, pipeline_item_id: str) -> dict[str, str]:
    rows = session.execute(
        select(PipelineReaderState.node_id, PipelineReaderState.cursor_value).where(
            PipelineReaderState.tenant_id == tenant_id,
            PipelineReaderState.pipeline_item_id == pipeline_item_id,
        )
    ).all()
    return {node_id: value for node_id, value in rows}


def upsert_reader_states(
    session: Session, *, tenant_id: str, pipeline_item_id: str, cursors: dict[str, str]
) -> None:
    existing = {
        r.node_id: r
        for r in session.execute(
            select(PipelineReaderState).where(
                PipelineReaderState.tenant_id == tenant_id,
                PipelineReaderState.pipeline_item_id == pipeline_item_id,
            )
        ).scalars()
    }
    for node_id, value in cursors.items():
        row = existing.get(node_id)
        if row is None:
            session.add(
                PipelineReaderState(
                    id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    pipeline_item_id=pipeline_item_id,
                    node_id=node_id,
                    cursor_value=value,
                )
            )
        else:
            row.cursor_value = value
            row.updated_at = _now()
    session.flush()


def delete_reader_states(
    session: Session, *, tenant_id: str, pipeline_item_id: str, node_id: str | None = None
) -> int:
    stmt = delete(PipelineReaderState).where(
        PipelineReaderState.tenant_id == tenant_id,
        PipelineReaderState.pipeline_item_id == pipeline_item_id,
    )
    if node_id is not None:
        stmt = stmt.where(PipelineReaderState.node_id == node_id)
    result = session.execute(stmt)
    session.flush()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
