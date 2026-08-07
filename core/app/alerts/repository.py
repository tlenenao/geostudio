# SPDX-License-Identifier: Apache-2.0
"""Mirrors app.pipelines.repository (SP-15a/h) exactly: "last evaluation"
is always derived from alert_evaluations (never a duplicated column on the
config), and list_due_rules reuses the same reclaim-by-age discipline as
list_due_pipelines — a "pending" evaluation older than
_PENDING_RECLAIM_MINUTES is presumed stuck and becomes eligible again."""
import uuid
from datetime import datetime, timedelta, timezone

import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.models import AlertEvaluation
from app.configs import repository as configs_repo

_PENDING_RECLAIM_MINUTES = 60


def create_evaluation(session: Session, *, tenant_id: str, alert_rule_item_id: str) -> AlertEvaluation:
    evaluation = AlertEvaluation(
        id=uuid.uuid4().hex, tenant_id=tenant_id, alert_rule_item_id=alert_rule_item_id,
        state="pending",
    )
    session.add(evaluation)
    session.flush()
    session.refresh(evaluation)
    return evaluation


def mark_evaluated(
    session: Session, *, evaluation_id: str, value: float | None, state: str, transitioned: bool,
    error: str | None = None,
) -> None:
    evaluation = session.get(AlertEvaluation, evaluation_id)
    if evaluation is None:
        return
    evaluation.value = value
    evaluation.state = state
    evaluation.transitioned = transitioned
    evaluation.error = error
    session.flush()


def get_evaluation(session: Session, *, tenant_id: str, evaluation_id: str) -> AlertEvaluation | None:
    return session.execute(
        select(AlertEvaluation).where(
            AlertEvaluation.id == evaluation_id, AlertEvaluation.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def get_latest_evaluation(
    session: Session, *, tenant_id: str, alert_rule_item_id: str,
) -> AlertEvaluation | None:
    return session.execute(
        select(AlertEvaluation)
        .where(
            AlertEvaluation.tenant_id == tenant_id,
            AlertEvaluation.alert_rule_item_id == alert_rule_item_id,
        )
        .order_by(AlertEvaluation.created_at.desc())
        .limit(1)
    ).scalars().first()


def list_evaluations(
    session: Session, *, tenant_id: str, alert_rule_item_id: str,
) -> list[AlertEvaluation]:
    rows = session.execute(
        select(AlertEvaluation)
        .where(
            AlertEvaluation.tenant_id == tenant_id,
            AlertEvaluation.alert_rule_item_id == alert_rule_item_id,
        )
        .order_by(AlertEvaluation.created_at.desc())
    ).scalars().all()
    return list(rows)


def list_due_rules(session: Session) -> list[tuple[str, str]]:
    """Cross-tenant sweep, consumed by sweep_alert_rules_task (app.alerts.jobs,
    Task 9). Never exposed via a route (same discipline as
    list_due_pipelines): the tuple carries tenant_id in clear."""
    now = datetime.now(timezone.utc)
    due: list[tuple[str, str]] = []
    for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="alert"):
        payload = config.alert
        if payload is None:
            continue
        policy = payload.refreshPolicy
        if not policy.enabled:
            continue
        latest = get_latest_evaluation(session, tenant_id=tenant_id, alert_rule_item_id=item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if latest.state == "pending":
            if (now - created_at) < timedelta(minutes=_PENDING_RECLAIM_MINUTES):
                continue
            due.append((item_id, tenant_id))
            continue
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due
