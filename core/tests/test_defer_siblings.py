# SPDX-License-Identifier: Apache-2.0
"""Jumelles de `defer_resilient` (L1b/L6, piège n°14) : un `.defer()` qui échoue donne un 503
propre aux routes, et ne prive jamais les éléments suivants d'un balayage."""

import pytest
from fastapi import HTTPException

from app.alerts import jobs as alert_jobs
from app.harvest import jobs as harvest_jobs
from app.harvest import routes as harvest_routes
from app.quality import jobs as quality_jobs

from .test_alert_sweep import _make_session, _seed_due_rule


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr("app.jobs.defer.time.sleep", lambda _s: None)


def test_harvest_run_deferrer_gives_503_when_the_queue_is_down(monkeypatch):
    def down(**_kw):
        raise RuntimeError("pool fermé")

    monkeypatch.setattr(harvest_routes.run_harvest_task, "defer", down)
    with pytest.raises(HTTPException) as e:
        harvest_routes.get_task_deferrer()("s1", "t1")
    assert e.value.status_code == 503


def test_alert_sweep_goes_on_after_one_failed_defer(monkeypatch):
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        _seed_due_rule(s, tenant_id=tenant.id, owner_id=user.id)
        _seed_due_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()
    calls: list[dict] = []

    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise RuntimeError("pool fermé")

    monkeypatch.setattr(alert_jobs.evaluate_alert_task, "defer", flaky)
    monkeypatch.setattr(alert_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(alert_jobs, "is_read_only_mode", lambda: False)
    alert_jobs.sweep_alert_rules_task(timestamp=0)
    assert len(calls) == 2


def test_sweeps_of_harvest_and_quality_swallow_a_failed_defer_per_item(monkeypatch):
    Session = _make_session()
    monkeypatch.setattr(harvest_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(harvest_jobs, "is_read_only_mode", lambda: False)

    class Src:
        def __init__(self, i):
            self.id, self.tenant_id = i, "t"

    monkeypatch.setattr(
        harvest_jobs.harvest_repo, "list_due_sources", lambda _s: [Src("a"), Src("b")]
    )
    seen: list[str] = []

    def flaky(source_id, tenant_id):
        seen.append(source_id)
        if source_id == "a":
            raise RuntimeError("down")

    monkeypatch.setattr(harvest_jobs.run_harvest_task, "defer", flaky)
    harvest_jobs.run_harvest_sweep_task(timestamp=0)
    assert seen == ["a", "b"]

    monkeypatch.setattr(quality_jobs, "session_factory", lambda: Session)
    monkeypatch.setattr(quality_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(quality_jobs.quality_repo, "reclaim_stuck_running", lambda _s: 0)
    monkeypatch.setattr(
        quality_jobs.quality_repo, "stale_pending_ids", lambda _s: [("r1", "t"), ("r2", "t")]
    )
    seen.clear()

    def flaky_q(report_id, tenant_id):
        seen.append(report_id)
        if report_id == "r1":
            raise RuntimeError("down")

    monkeypatch.setattr(quality_jobs.run_quality_check_task, "defer", flaky_q)
    quality_jobs.sweep_quality_reports_task(timestamp=0)
    assert seen == ["r1", "r2"]
