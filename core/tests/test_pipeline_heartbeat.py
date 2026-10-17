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


def _running(session, tenant, item):
    run = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
    session.commit()
    assert pipelines_repo.mark_running(session, run_id=run.id)
    session.commit()
    return run


def test_mark_failed_if_queued_never_overwrites_a_running_run():
    """AUD-025 (I3)."""
    session, tenant, _, item = _env()
    run = _running(session, tenant, item)
    assert not pipelines_repo.mark_failed_if_queued(session, run_id=run.id, error="x")
    session.refresh(run)
    assert run.status == "running" and run.error is None


def test_mark_failed_if_queued_fails_a_queued_run():
    session, tenant, _, item = _env()
    run = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
    session.commit()
    assert pipelines_repo.mark_failed_if_queued(session, run_id=run.id, error="x")
    session.commit()
    session.refresh(run)
    assert run.status == "failed" and run.error == "x" and run.finished_at is not None


def test_mark_running_after_retrying_resets_the_heartbeat():
    """AUD-026 (I1) : pas de battement périmé hérité de la tentative précédente."""
    session, tenant, _, item = _env()
    run = _running(session, tenant, item)
    run.heartbeat_at = pipelines_repo._now() - timedelta(hours=3)
    run.status = "retrying"
    session.commit()
    assert pipelines_repo.mark_running(session, run_id=run.id)
    session.commit()
    session.refresh(run)
    assert run.heartbeat_at is None
    assert pipelines_repo.reclaim_stuck_runs(session) == 0  # ancré sur started_at récent


def test_heartbeat_thread_beats_immediately_then_periodically(monkeypatch):
    """AUD-026 : exerce réellement `_heartbeat` (période patchée)."""
    import time

    from app.pipelines import jobs as pipeline_jobs

    beats = []
    monkeypatch.setattr(pipeline_jobs, "_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(
        pipeline_jobs.pipelines_repo, "touch_heartbeat", lambda s, run_id: beats.append(run_id)
    )

    class Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pipeline_jobs, "request_scoped_session", lambda f: Ctx())
    with pipeline_jobs._heartbeat(object(), "r1"):
        time.sleep(0.3)
    n = len(beats)
    assert n >= 3 and set(beats) == {"r1"}
    time.sleep(0.15)
    assert len(beats) == n  # arrêté à la sortie du contexte
