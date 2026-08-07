# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pipelines.models import PipelineRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun:
    run = PipelineRun(
        id=uuid.uuid4().hex, tenant_id=tenant_id, pipeline_item_id=pipeline_item_id,
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


def list_runs(session: Session, *, tenant_id: str, pipeline_item_id: str) -> list[PipelineRun]:
    rows = session.execute(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id)
        .order_by(PipelineRun.created_at.desc())
    ).scalars().all()
    return list(rows)


def mark_running(session: Session, *, run_id: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "running"
    run.started_at = _now()
    session.flush()


def mark_succeeded(session: Session, *, run_id: str, node_stats: dict) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "succeeded"
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


def append_node_stat(session: Session, *, tenant_id: str, run_id: str, node_id: str, stat: dict) -> None:
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
