# SPDX-License-Identifier: Apache-2.0
"""sweep_alert_rules_task (SP-16b) — mirrors test_pipeline_sweep.py exactly:
pure SQLite, evaluate_alert_task.defer is monkeypatched so this test proves
"is a rule due, was create_evaluation+defer called correctly", never a real
evaluation (covered by test_alert_jobs.py, postgis-marked)."""

from app.alerts import jobs as alert_jobs
from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _alert_body(refresh_policy=None) -> dict:
    return {
        "kind": "alert",
        "alert": {
            "datasetItemId": "ds-1",
            "query": {"agg": "count"},
            "condition": {"expr": "value > 100"},
            "refreshPolicy": refresh_policy or {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }


def _seed_due_rule(session, *, tenant_id, owner_id):
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="alert",
        title="Rule",
    )
    config = BuilderConfig.model_validate(_alert_body())
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_sweep_defers_evaluate_alert_task_for_a_due_rule(monkeypatch):
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
        rule_id = _seed_due_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(alert_jobs.evaluate_alert_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(alert_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(alert_jobs, "is_read_only_mode", lambda: False)

    alert_jobs.sweep_alert_rules_task(timestamp=0)

    assert len(deferred) == 1
    assert deferred[0]["tenant_id"] == tenant.id
    with Session() as s:
        evaluation = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_id
        )
        assert evaluation is not None
        assert evaluation.state == "pending"
        assert evaluation.id == deferred[0]["evaluation_id"]


def test_sweep_defers_nothing_when_no_rule_is_due(monkeypatch):
    Session = _make_session()
    deferred = []
    monkeypatch.setattr(alert_jobs.evaluate_alert_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(alert_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(alert_jobs, "is_read_only_mode", lambda: False)

    alert_jobs.sweep_alert_rules_task(timestamp=0)

    assert deferred == []


def test_sweep_short_circuits_in_read_only_mode(monkeypatch):
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
        s.commit()

    deferred = []
    monkeypatch.setattr(alert_jobs.evaluate_alert_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(alert_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(alert_jobs, "is_read_only_mode", lambda: True)

    alert_jobs.sweep_alert_rules_task(timestamp=0)

    assert deferred == []


def test_sweep_commits_evaluation_before_deferring(monkeypatch, tmp_path):
    # Same rationale as test_pipeline_sweep.py::test_sweep_commits_run_before_deferring —
    # two distinct sqlite file-backed engines for real transactional isolation.
    db_url = f"sqlite+pysqlite:///{tmp_path / 'alert_sweep.db'}"
    main_engine = make_engine(db_url)
    init_db(main_engine)
    Session = make_session_factory(main_engine)
    separate_engine = make_engine(db_url)
    SeparateSession = make_session_factory(separate_engine)

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
        s.commit()
        tenant_id = tenant.id

    seen_from_separate_session = []

    def fake_defer(**kw):
        with SeparateSession() as s2:
            evaluation = alerts_repo.get_evaluation(
                s2, tenant_id=tenant_id, evaluation_id=kw["evaluation_id"]
            )
            seen_from_separate_session.append(evaluation is not None)

    monkeypatch.setattr(alert_jobs.evaluate_alert_task, "defer", fake_defer)
    monkeypatch.setattr(alert_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(alert_jobs, "is_read_only_mode", lambda: False)

    alert_jobs.sweep_alert_rules_task(timestamp=0)

    assert seen_from_separate_session == [True]


def test_previous_terminal_state_skips_stuck_pending_rows_after_reclaim():
    # Regression for SP-16b Task 9's remaining bug: list_due_rules reclaims a
    # "pending" evaluation stuck for > _PENDING_RECLAIM_MINUTES (worker crash,
    # restart loop) and creates a fresh one. evaluate_alert_task's history
    # then looks like [current (pending), stuck-old (pending), ...real
    # terminal states...] — skipping only the current row (by id) leaves the
    # stuck-old pending row as "previous", and the existing
    # "previous_state == pending -> transitioned" fallback fires a spurious
    # re-notification even though the rule's real state (firing) never
    # changed. _previous_terminal_state must walk past BOTH pending rows and
    # land on the real "firing" evaluation underneath.
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
        rule_id = _seed_due_rule(s, tenant_id=tenant.id, owner_id=user.id)

        old_real = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(
            s, evaluation_id=old_real.id, value=5.0, state="firing", transitioned=True
        )

        stuck = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        # stuck stays "pending" — never reached mark_evaluated, as if the
        # worker that picked it up crashed mid-evaluation.

        current = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        s.commit()

        history = alerts_repo.list_evaluations(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        assert [e.id for e in history] == [current.id, stuck.id, old_real.id]  # most-recent-first

        previous_state = alert_jobs._previous_terminal_state(
            history, current_evaluation_id=current.id
        )
        assert previous_state == "firing"

        # Same formula evaluate_alert_task uses: stable firing -> firing
        # across the reclaim must NOT count as a transition.
        transitioned = previous_state is None or previous_state != "firing"
        assert transitioned is False
