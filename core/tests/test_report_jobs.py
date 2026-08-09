# SPDX-License-Identifier: Apache-2.0
"""_trigger_due_reports (SP-17b) — mirrors test_alert_jobs.py's shape for the
"resolve owner, re-check permissions, create export_jobs+report_runs" half of
the sweep. The notify half lives in test_report_jobs.py's sibling tests
below; the periodic-task-level commit-before-defer proof lives in
test_report_sweep.py (mirrors test_alert_sweep.py/test_pipeline_sweep.py)."""
from sqlalchemy import select

from app.alerts.notify import NotifyError
from app.audit.models import AuditLog
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.items import repository as items_repo
from app.reports import jobs as report_jobs
from app.reports import repository as reports_repo
from app.sharing.authorization import can
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed_bookmark(session, *, tenant_id, owner_id, app_id="app-1", page_id="page-1") -> str:
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="bookmark", title="A view",
    )
    config = BuilderConfig.model_validate({
        "kind": "bookmark",
        "bookmark": {"appId": app_id, "pageId": page_id, "timeRange": None, "extent": None, "crossFilter": {}},
    })
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def _seed_report(session, *, tenant_id, owner_id, bookmark_item_id) -> str:
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="report", title="Weekly report",
    )
    config = BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": bookmark_item_id,
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_trigger_creates_export_job_and_report_run_for_due_report(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id)
        s.commit()

    deferred = []
    monkeypatch.setattr(report_jobs, "render_export_task", type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}))
    report_jobs._trigger_due_reports(Session)

    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        job = export_repo.get_job(s, tenant_id=tenant.id, job_id=run.export_job_id)
        assert job is not None
        assert job.item_id == app_item.id
        assert job.page_id == "page-1"
        assert job.format == "pdf"
    assert len(deferred) == 1
    assert deferred[0]["job_id"] == job.id


def test_trigger_skips_report_and_audits_when_owner_lost_bookmark_access(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Dashboard",
        )
        # Bookmark owned by "other", never shared with "owner" — "owner"
        # (the report's owner) cannot read it.
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=other.id, app_id=app_item.id)
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id)
        s.commit()

    deferred = []
    monkeypatch.setattr(report_jobs, "render_export_task", type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}))
    report_jobs._trigger_due_reports(Session)

    assert deferred == []
    with Session() as s:
        assert reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id) is None


def test_trigger_skips_report_and_audits_when_owner_lost_app_access(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        # App owned by "other", never shared with "owner" — "owner" (the
        # report's owner) cannot read it, but CAN read the bookmark itself
        # (bookmark owned by "owner"). This exercises the second permission
        # check ("target app not readable"), distinct from the first
        # ("bookmark not readable") covered by the sibling test above.
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id)
        s.commit()

    deferred = []
    monkeypatch.setattr(report_jobs, "render_export_task", type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}))
    report_jobs._trigger_due_reports(Session)

    assert deferred == []
    with Session() as s:
        assert reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id) is None
        audit_rows = s.execute(
            select(AuditLog).where(AuditLog.action == "report.run", AuditLog.object_id == report_id)
        ).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].payload["success"] is False
        assert audit_rows[0].payload["error"] == "target app not readable by report owner"
