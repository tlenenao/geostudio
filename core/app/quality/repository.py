# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.job_timeouts import running_reclaim_minutes
from app.quality.models import QualityReport, _now

_TERMINAL = ("done", "failed")
BATCH = 100
PENDING_RETRY_MINUTES = 5


def create_report(
    session: Session, *, tenant_id: str, collection_id: str, requested_by: str, masked: bool
) -> QualityReport:
    report = QualityReport(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        collection_id=collection_id,
        requested_by=requested_by,
        masked=masked,
        status="pending",
    )
    session.add(report)
    session.flush()
    session.refresh(report)
    return report


def get_report(session: Session, report_id: str, tenant_id: str) -> QualityReport | None:
    return session.execute(
        select(QualityReport).where(
            QualityReport.id == report_id, QualityReport.tenant_id == tenant_id
        )
    ).scalar_one_or_none()


def list_reports(
    session: Session, *, tenant_id: str, collection_id: str, limit: int = 20
) -> list[QualityReport]:
    return list(
        session.execute(
            select(QualityReport)
            .where(
                QualityReport.tenant_id == tenant_id, QualityReport.collection_id == collection_id
            )
            .order_by(QualityReport.created_at.desc())
            .limit(limit)
        ).scalars()
    )


def mark_running(session: Session, report_id: str) -> bool:
    """`pending -> running` conditionnel ; False si le rapport n'est plus prenable."""
    result = session.execute(
        update(QualityReport)
        .where(QualityReport.id == report_id, QualityReport.status == "pending")
        .values(status="running", started_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(
    session: Session, report_id: str, *, checked: int, summary: dict, violations: list
) -> bool:
    result = session.execute(
        update(QualityReport)
        .where(QualityReport.id == report_id, QualityReport.status.notin_(_TERMINAL))
        .values(
            status="done",
            checked=checked,
            summary=summary,
            violations=violations,
            finished_at=_now(),
        )
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_failed(session: Session, report_id: str, error: str) -> bool:
    result = session.execute(
        update(QualityReport)
        .where(QualityReport.id == report_id, QualityReport.status.notin_(_TERMINAL))
        .values(status="failed", error=error, finished_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def stale_pending_ids(session: Session) -> list[tuple[str, str]]:
    """`pending` dont le defer a été perdu (commit puis defer, piège n°14)."""
    threshold = _now() - timedelta(minutes=PENDING_RETRY_MINUTES)
    rows = session.execute(
        select(QualityReport.id, QualityReport.tenant_id)
        .where(QualityReport.status == "pending", QualityReport.created_at < threshold)
        .limit(BATCH)
    ).all()
    return [(r.id, r.tenant_id) for r in rows]


def reclaim_stuck_running(session: Session) -> list[str]:
    """`running` sans fin depuis trop longtemps (worker tué) -> `failed`, compare-and-swap
    sur started_at."""
    threshold = _now() - timedelta(minutes=running_reclaim_minutes())
    rows = session.execute(
        select(QualityReport.id, QualityReport.started_at)
        .where(QualityReport.status == "running", QualityReport.started_at < threshold)
        .limit(BATCH)
    ).all()
    reclaimed: list[str] = []
    for report_id, started_at in rows:
        claimed = session.execute(
            update(QualityReport)
            .where(
                QualityReport.id == report_id,
                QualityReport.status == "running",
                QualityReport.started_at == started_at,
            )
            .values(
                status="failed",
                error="quality check timed out (worker crashed or hung)",
                finished_at=_now(),
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(report_id)
    session.flush()
    return reclaimed
