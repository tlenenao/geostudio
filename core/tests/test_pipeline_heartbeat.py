# SPDX-License-Identifier: Apache-2.0
"""AUD-026 : le balayage ancre un run `running` sur son battement de cœur."""

from datetime import timedelta

from app.pipelines import repository as pipelines_repo
from tests.test_reclaim_pending_jobs import _env


def _running_run(session, tenant, item, *, heartbeat_age_h):
    run = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
    now = pipelines_repo._now()
    run.status = "running"
    run.started_at = now - timedelta(hours=2)
    run.heartbeat_at = now - timedelta(hours=heartbeat_age_h)
    session.commit()
    return run


def test_run_with_fresh_heartbeat_is_not_reclaimed():
    session, tenant, _, item = _env()
    run = _running_run(session, tenant, item, heartbeat_age_h=0)
    assert pipelines_repo.reclaim_stuck_runs(session) == 0
    session.refresh(run)
    assert run.status == "running"


def test_run_with_stale_heartbeat_is_reclaimed():
    session, tenant, _, item = _env()
    run = _running_run(session, tenant, item, heartbeat_age_h=2)
    assert pipelines_repo.reclaim_stuck_runs(session) == 1
    session.commit()
    session.refresh(run)
    assert run.status == "failed"


def test_touch_heartbeat_updates_running_run_only():
    session, tenant, _, item = _env()
    run = _running_run(session, tenant, item, heartbeat_age_h=2)
    pipelines_repo.touch_heartbeat(session, run_id=run.id)
    session.commit()
    session.refresh(run)
    assert abs(
        pipelines_repo._now().replace(tzinfo=None) - run.heartbeat_at.replace(tzinfo=None)
    ) < timedelta(minutes=1)
    run.status = "succeeded"
    run.heartbeat_at = None
    session.commit()
    pipelines_repo.touch_heartbeat(session, run_id=run.id)
    session.commit()
    session.refresh(run)
    assert run.heartbeat_at is None
