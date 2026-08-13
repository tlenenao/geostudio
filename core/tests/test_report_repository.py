# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _report_body(cron="*/5 * * * *", enabled=True) -> dict:
    return {
        "kind": "report",
        "report": {
            "bookmarkItemId": "bookmark-1",
            "refreshPolicy": {"enabled": enabled, "cron": cron},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }


def _seed_report(session, *, tenant_id, owner_id, **body_kwargs) -> str:
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="report", title="Report",
    )
    config = BuilderConfig.model_validate(_report_body(**body_kwargs))
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_create_run_and_get_run_round_trip():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-1")
        s.commit()

        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched is not None
        assert fetched.export_job_id == "job-1"
        assert fetched.notified_at is None


def test_list_runs_orders_most_recent_first():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        first = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-1")
        second = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-2")
        s.commit()

        runs = reports_repo.list_runs(s, tenant_id=tenant.id, report_item_id=report_id)
        assert [r.id for r in runs] == [second.id, first.id]


def test_get_latest_run_returns_none_when_no_run_exists():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        assert reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id) is None


def test_mark_notified_sets_timestamp():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-1")
        s.commit()

        reports_repo.mark_notified(s, run_id=run.id)
        s.commit()

        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None


def test_list_unnotified_runs_excludes_already_notified():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        notified = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-1")
        pending = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-2")
        s.commit()
        reports_repo.mark_notified(s, run_id=notified.id)
        s.commit()

        unnotified = reports_repo.list_unnotified_runs(s)
        assert [r.id for r in unnotified] == [pending.id]


def test_list_due_reports_returns_report_with_no_prior_run():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

        due = reports_repo.list_due_reports(s)
        assert (report_id, tenant.id) in due


def test_list_due_reports_ignores_disabled_refresh_policy():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_report(s, tenant_id=tenant.id, owner_id=user.id, enabled=False)
        s.commit()

        assert reports_repo.list_due_reports(s) == []


def test_list_due_reports_respects_cron_cadence_against_last_run():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        # Every 5 minutes, but the only run is 1 minute old — not due yet.
        report_id = _seed_report(s, tenant_id=tenant.id, owner_id=user.id, cron="*/5 * * * *")
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id="job-1")
        s.commit()
        run.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.commit()

        assert reports_repo.list_due_reports(s) == []
