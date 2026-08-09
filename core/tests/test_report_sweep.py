# SPDX-License-Identifier: Apache-2.0
"""sweep_report_schedules_task (SP-17b) — mirrors test_alert_sweep.py/
test_pipeline_sweep.py exactly: pure SQLite, render_export_task.defer is
monkeypatched so this test proves "is a report due, was export_jobs+
report_runs created and committed before deferring", never a real render."""
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports import jobs as report_jobs
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed_due_report(session, *, tenant_id, owner_id) -> str:
    app_item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="app", title="Dashboard",
    )
    bookmark_item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="bookmark", title="A view",
    )
    bookmark_config = BuilderConfig.model_validate({
        "kind": "bookmark",
        "bookmark": {"appId": app_item.id, "pageId": "page-1", "timeRange": None, "extent": None, "crossFilter": {}},
    })
    configs_repo.create_config(session, bookmark_config, item_id=bookmark_item.id, tenant_id=tenant_id)

    report_item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="report", title="Weekly report",
    )
    report_config = BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": bookmark_item.id,
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })
    configs_repo.create_config(session, report_config, item_id=report_item.id, tenant_id=tenant_id)
    return report_item.id


def test_sweep_defers_render_export_task_for_a_due_report(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_due_report(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(report_jobs.render_export_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(report_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(report_jobs, "is_read_only_mode", lambda: False)

    report_jobs.sweep_report_schedules_task(timestamp=0)

    assert len(deferred) == 1
    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is not None


def test_sweep_short_circuits_in_read_only_mode(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_report(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(report_jobs.render_export_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(report_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(report_jobs, "is_read_only_mode", lambda: True)

    report_jobs.sweep_report_schedules_task(timestamp=0)

    assert deferred == []


def test_sweep_commits_run_before_deferring(monkeypatch, tmp_path):
    # Same rationale as test_alert_sweep.py::test_sweep_commits_evaluation_before_deferring.
    db_url = f"sqlite+pysqlite:///{tmp_path / 'report_sweep.db'}"
    main_engine = make_engine(db_url)
    init_db(main_engine)
    Session = make_session_factory(main_engine)
    separate_engine = make_engine(db_url)
    SeparateSession = make_session_factory(separate_engine)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_report(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()
        tenant_id = tenant.id

    seen_from_separate_session = []

    def fake_defer(**kw):
        from app.export import repository as export_repo
        with SeparateSession() as s2:
            job = export_repo.get_job(s2, tenant_id=tenant_id, job_id=kw["job_id"])
            seen_from_separate_session.append(job is not None)

    monkeypatch.setattr(report_jobs.render_export_task, "defer", fake_defer)
    monkeypatch.setattr(report_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(report_jobs, "is_read_only_mode", lambda: False)

    report_jobs.sweep_report_schedules_task(timestamp=0)

    assert seen_from_separate_session == [True]
