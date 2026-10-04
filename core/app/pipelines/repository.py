# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

import croniter
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, aliased

from app.configs import repository as configs_repo
from app.pipelines.models import PipelineRun, PipelineWebhookToken


def _now() -> datetime:
    return datetime.now(UTC)


_RUNNING_RECLAIM_MINUTES = 60


def create_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun:
    run = PipelineRun(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        pipeline_item_id=pipeline_item_id,
        status="queued",
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


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
        .where(PipelineRun.id == run_id, PipelineRun.status.in_(("queued", "pending")))
        .values(status="running", started_at=_now(), finished_at=None, error=None)
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

    if not _transition("queued", status="cancelled", finished_at=_now()):
        _transition("running", status="cancel_requested")
    session.flush()
    session.refresh(run)
    return run.status


def is_cancel_requested(session: Session, *, run_id: str) -> bool:
    run = session.get(PipelineRun, run_id)
    return run is not None and run.status == "cancel_requested"


def mark_cancelled(session: Session, *, run_id: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "cancelled"
    run.finished_at = _now()
    session.flush()


def mark_succeeded(session: Session, *, run_id: str, node_stats: dict) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "succeeded"
    run.error = None  # run vivant clos à tort par reclaim_stuck_runs : la fin réelle prime
    run.finished_at = _now()
    run.node_stats = node_stats
    session.flush()


def mark_failed(session: Session, *, run_id: str, error: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "failed"
    run.finished_at = _now()
    run.error = error
    session.flush()


def reclaim_stuck_runs(
    session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES
) -> int:
    """Clôt en erreur les runs « queued » (jamais pris en charge : defer perdu,
    file non consommée — P01.04) ou « running » (ancrés sur started_at —
    c02-005 : sans cela l'ancien run restait zombie à côté du nouveau) plus
    vieux que le seuil. Cross-tenant, appelée par le balayage cron. UPDATE
    conditionnel sur le statut : un run terminé entre-temps n'est pas touché.
    # ponytail: pas de heartbeat — un run vivant de plus de
    # _RUNNING_RECLAIM_MINUTES est aussi clos ; heartbeat si des pipelines
    # légitimes dépassent ce délai."""
    threshold = _now() - timedelta(minutes=older_than_minutes)
    anchor = case(
        (PipelineRun.status.in_(("running", "cancel_requested")), PipelineRun.started_at),
        else_=PipelineRun.created_at,
    )
    result = session.execute(
        update(PipelineRun)
        .where(
            PipelineRun.status.in_(("queued", "running", "cancel_requested")),
            func.coalesce(anchor, PipelineRun.created_at) < threshold,
        )
        .values(
            status="failed",
            finished_at=_now(),
            error="run périmé : jamais terminé, clos par le balayage de planification",
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


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


def list_due_pipelines(session: Session) -> list[tuple[str, str]]:
    """Balayage cross-tenant des pipelines planifiés dus, consommé par
    run_pipeline_sweep_task (app.pipelines.jobs, SP-15h). "Dernier run"
    dérivé de pipeline_runs (jamais une colonne dupliquée) ; garde de
    concurrence par âge identique à app.harvest.repository.list_due_sources
    (_RUNNING_RECLAIM_MINUTES) — un run resté "running"/"queued" plus vieux
    que ce délai est présumé planté et redevient éligible."""
    now = datetime.now(UTC)
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
    latest_by_item = get_latest_runs_for_items(session, item_ids=[c[0] for c in candidates])
    for item_id, tenant_id, config in candidates:
        payload = config.pipeline
        policy = payload.refreshPolicy
        latest = latest_by_item.get(item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if latest.status in ("queued", "running", "cancel_requested"):
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
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due


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
