# SPDX-License-Identifier: Apache-2.0
"""Mirrors app.pipelines.repository (SP-15a/h) and app.alerts.repository
(SP-16b): "last run" is always derived from report_runs (never a duplicated
column on the config), list_due_reports reuses the same croniter-against-
last-created_at pattern as list_due_pipelines. Unlike ReportRun's sibling
tables, there is no "pending"/"running" status to reclaim here — a
report_runs row is only ever created immediately before its export_jobs row
is deferred (see app.reports.jobs), so there is no stuck-intermediate-state
window to guard against; a stuck render itself is already covered by
export_repo.reclaim_stuck_jobs (SP-17a)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.reports.models import ReportRun

import croniter


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, *, tenant_id: str, report_item_id: str, export_job_id: str) -> ReportRun:
    run = ReportRun(
        id=uuid.uuid4().hex, tenant_id=tenant_id,
        report_item_id=report_item_id, export_job_id=export_job_id,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def get_run(session: Session, *, tenant_id: str, run_id: str) -> ReportRun | None:
    return session.execute(
        select(ReportRun).where(ReportRun.id == run_id, ReportRun.tenant_id == tenant_id)
    ).scalar_one_or_none()


def list_runs(session: Session, *, tenant_id: str, report_item_id: str) -> list[ReportRun]:
    rows = session.execute(
        select(ReportRun)
        .where(ReportRun.tenant_id == tenant_id, ReportRun.report_item_id == report_item_id)
        .order_by(ReportRun.created_at.desc())
    ).scalars().all()
    return list(rows)


def get_latest_run(session: Session, *, tenant_id: str, report_item_id: str) -> ReportRun | None:
    return session.execute(
        select(ReportRun)
        .where(ReportRun.tenant_id == tenant_id, ReportRun.report_item_id == report_item_id)
        .order_by(ReportRun.created_at.desc())
        .limit(1)
    ).scalars().first()


def mark_notified(session: Session, *, run_id: str) -> None:
    run = session.get(ReportRun, run_id)
    if run is None:
        return
    run.notified_at = _now()
    session.flush()


def list_unnotified_runs(session: Session) -> list[ReportRun]:
    """Cross-tenant sweep, consumed by sweep_report_schedules_task's notify
    step — same discipline as list_due_reports below: never exposed via a
    route, the caller is a system task, not a user request."""
    rows = session.execute(
        select(ReportRun).where(ReportRun.notified_at.is_(None))
    ).scalars().all()
    return list(rows)


def list_due_reports(session: Session) -> list[tuple[str, str]]:
    """Cross-tenant sweep, consumed by sweep_report_schedules_task's trigger
    step. Never exposed via a route (same discipline as list_due_pipelines/
    list_due_rules): the tuple carries tenant_id in clear."""
    now = datetime.now(timezone.utc)
    due: list[tuple[str, str]] = []
    for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="report"):
        payload = config.report
        if payload is None:
            continue
        policy = payload.refreshPolicy
        if not policy.enabled:
            continue
        latest = get_latest_run(session, tenant_id=tenant_id, report_item_id=item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due
