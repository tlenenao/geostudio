# SPDX-License-Identifier: Apache-2.0
"""_trigger_due_reports (SP-17b) — mirrors test_alert_jobs.py's shape for the
"resolve owner, re-check permissions, create export_jobs+report_runs" half of
the sweep. The notify half lives in test_report_jobs.py's sibling tests
below; the periodic-task-level commit-before-defer proof lives in
test_report_sweep.py (mirrors test_alert_sweep.py/test_pipeline_sweep.py)."""

import pytest
from sqlalchemy import select

from app.alerts.notify import NotifyError
from app.audit.models import AuditLog
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.items import repository as items_repo
from app.notifications import repository as notifications_repo
from app.notifications.models import Notification
from app.reports import jobs as report_jobs
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def _export_enabled(monkeypatch):
    """Le balayage refuse de déclencher un rendu quand la capacité export est
    coupée (revue finale SP-17b, I3) — ces tests décrivent une instance où
    elle est active ; le cas coupé a son propre test."""
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed_bookmark(session, *, tenant_id, owner_id, app_id="app-1", page_id="page-1") -> str:
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="bookmark",
        title="A view",
    )
    config = BuilderConfig.model_validate(
        {
            "kind": "bookmark",
            "bookmark": {
                "appId": app_id,
                "pageId": page_id,
                "timeRange": None,
                "extent": None,
                "crossFilter": {},
            },
        }
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def _seed_report(session, *, tenant_id, owner_id, bookmark_item_id) -> str:
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="report",
        title="Weekly report",
    )
    config = BuilderConfig.model_validate(
        {
            "kind": "report",
            "report": {
                "bookmarkItemId": bookmark_item_id,
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        }
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_trigger_creates_export_job_and_report_run_for_due_report(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    deferred = []
    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )
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
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        other = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=other.id,
            resource_type="app",
            title="Dashboard",
        )
        # Bookmark owned by "other", never shared with "owner" — "owner"
        # (the report's owner) cannot read it.
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=other.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    deferred = []
    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )
    report_jobs._trigger_due_reports(Session)

    assert deferred == []
    with Session() as s:
        # Une ligne report_runs existe malgré l'échec (revue finale SP-17b,
        # I2) mais sans export_job_id : rien n'a été rendu.
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None


def test_trigger_skips_report_and_audits_when_owner_lost_app_access(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        other = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        # App owned by "other", never shared with "owner" — "owner" (the
        # report's owner) cannot read it, but CAN read the bookmark itself
        # (bookmark owned by "owner"). This exercises the second permission
        # check ("target app not readable"), distinct from the first
        # ("bookmark not readable") covered by the sibling test above.
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=other.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    deferred = []
    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )
    report_jobs._trigger_due_reports(Session)

    assert deferred == []
    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None
        audit_rows = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.run", AuditLog.object_id == report_id
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].payload["success"] is False
        assert audit_rows[0].payload["error"] == "target app not readable by report owner"


def test_failed_trigger_still_records_a_run_so_cron_cadence_is_respected(monkeypatch):
    # Revue finale SP-17b (I2) : un déclenchement en échec n'écrivait qu'une
    # ligne d'audit, aucune ligne report_runs. list_due_reports dérivant
    # « dû ? » de get_latest_run, le rapport était rejugé dû à CHAQUE
    # balayage de 5 minutes au lieu de respecter son cron hebdomadaire.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        other = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        # Bookmark détenu par "other", jamais partagé : le propriétaire du
        # rapport ne peut pas le lire → ReportTriggerError à chaque tentative.
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=other.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=other.id, app_id=app_item.id)
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        )
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": bookmark_id,
                    "refreshPolicy": {"enabled": True, "cron": "0 8 * * 1"},  # hebdomadaire
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        report_id = item.id
        s.commit()

    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: None)}),
    )

    with Session() as s:
        assert (report_id, tenant.id) in reports_repo.list_due_reports(s)

    report_jobs._trigger_due_reports(Session)

    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None  # aucun rendu n'a été mis en file
        assert run.notified_at is not None  # rien à notifier : clos d'emblée
        # Même tick : le rapport n'est PLUS dû (avant le correctif, il l'était
        # encore, et le serait resté à chaque balayage de 5 minutes).
        assert (report_id, tenant.id) not in reports_repo.list_due_reports(s)


def test_trigger_continues_to_next_report_when_one_raises_an_unexpected_error(monkeypatch):
    # Revue finale SP-17b (I1) : seule ReportTriggerError était rattrapée.
    # render_export_task.defer (vrai appel Postgres/procrastinate),
    # write_audit et les session.commit() de la boucle ne l'étaient pas — un
    # incident transitoire sur le premier rapport abandonnait tous les
    # suivants, pour tous les tenants, et sautait reclaim_stuck_jobs.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        first_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        second_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    attempts = []

    def _defer(**kw):
        attempts.append(kw)
        if len(attempts) == 1:
            raise Exception("procrastinate indisponible")

    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(_defer)}),
    )

    report_jobs._trigger_due_reports(Session)  # ne doit pas propager

    # Les DEUX rapports dus ont été traités : avant le correctif, l'exception
    # du premier remontait et le second n'était jamais atteint.
    assert len(attempts) == 2
    with Session() as s:
        failures = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.run", AuditLog.object_type == "item"
                )
            )
            .scalars()
            .all()
        )
        assert len(failures) == 1
        assert failures[0].payload["success"] is False
        assert "mise en file impossible" in failures[0].payload["error"]
        assert failures[0].object_id in {first_id, second_id}
        # Le job du rapport en échec est clos en erreur : sans ça il resterait
        # "pending" pour toujours (personne ne l'a dépilé, et
        # reclaim_stuck_jobs ne récupère que les "running").
        failed_run = reports_repo.get_latest_run(
            s,
            tenant_id=tenant.id,
            report_item_id=failures[0].object_id,
        )
        failed_job = export_repo.get_job(s, tenant_id=tenant.id, job_id=failed_run.export_job_id)
        assert failed_job.status == "error"


def test_trigger_audits_unexpected_error_raised_inside_the_loop_body(monkeypatch):
    # Second chemin d'I1 : l'erreur inattendue survient AVANT le commit
    # (ici encode_analytics_context), donc le filet large doit annuler les
    # écritures partielles, auditer « erreur interne » et continuer.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    deferred = []
    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )

    def _boom(bookmark):
        raise ValueError("bookmark illisible")

    monkeypatch.setattr(report_jobs, "encode_analytics_context", _boom)

    report_jobs._trigger_due_reports(Session)  # ne doit pas propager

    assert deferred == []
    with Session() as s:
        rows = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.run", AuditLog.object_id == report_id
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload["success"] is False
        assert rows[0].payload["error"] == "erreur interne : bookmark illisible"


def test_notify_sends_webhook_with_result_url_and_marks_notified(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        report_id = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s,
            tenant_id=tenant.id,
            item_id=app_item.id,
            user_id=owner.id,
            format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    sent = []
    monkeypatch.setattr(
        report_jobs, "send_webhook", lambda channel, *, payload: sent.append((channel, payload))
    )
    monkeypatch.setattr(
        report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-1.pdf"
    )
    report_jobs._notify_pending_reports(Session)

    assert len(sent) == 1
    assert sent[0][1]["resultUrl"] == "https://s3.test/renders/job-1.pdf"
    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None


def test_notify_marks_notified_even_when_channel_fails(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        report_id = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s,
            tenant_id=tenant.id,
            item_id=app_item.id,
            user_id=owner.id,
            format="pdf",
        )
        export_repo.mark_error(s, job_id=job.id, error="worker crashed")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    def _fail(*a, **kw):
        raise NotifyError("webhook unreachable")

    monkeypatch.setattr(report_jobs, "send_webhook", _fail)
    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None  # never retried, even on failure


def test_notify_marks_notified_when_channel_raises_a_non_notify_error(monkeypatch):
    # Revue finale SP-17b (C2) : send_email peut lever autre chose qu'une
    # NotifyError (KeyError/RuntimeError du chargement de la clé maître,
    # InvalidTag AES-GCM sur un secret corrompu), et _presigned_url_for_job
    # peut lever un KeyError si S3_ENDPOINT_URL est absent. Sans filet large,
    # l'exception s'échappait avant mark_notified et bloquait la notification
    # de TOUS les tenants pour toujours (list_unnotified_runs est
    # cross-tenant, non ordonnée, rejouée toutes les 5 minutes).
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        report_id = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s,
            tenant_id=tenant.id,
            item_id=app_item.id,
            user_id=owner.id,
            format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    def _boom(*a, **kw):
        raise RuntimeError("clé maître de secrets absente")

    monkeypatch.setattr(report_jobs, "send_webhook", _boom)
    monkeypatch.setattr(report_jobs, "_presigned_url_for_job", lambda job: None)

    report_jobs._notify_pending_reports(Session)  # ne doit pas propager

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None  # jamais rejoué, même sur erreur inattendue
        audit_rows = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.notify", AuditLog.object_id == report_id
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].payload["success"] is False
        assert audit_rows[0].payload["channel"] is None
        assert "clé maître de secrets absente" in audit_rows[0].payload["error"]


def test_notify_marks_notified_when_presigned_url_raises(monkeypatch):
    # Second chemin du même filet : l'échec vient d'AVANT la boucle de canaux
    # (_presigned_url_for_job lit os.environ["S3_ENDPOINT_URL"]).
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        report_id = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s,
            tenant_id=tenant.id,
            item_id=app_item.id,
            user_id=owner.id,
            format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    sent = []
    monkeypatch.setattr(
        report_jobs, "send_webhook", lambda channel, *, payload: sent.append(payload)
    )

    def _boom(job):
        raise KeyError("S3_ENDPOINT_URL")

    monkeypatch.setattr(report_jobs, "_presigned_url_for_job", _boom)

    report_jobs._notify_pending_reports(Session)

    assert sent == []
    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None


def test_notify_skips_runs_whose_export_job_is_still_pending():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        report_id = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="report",
            title="Weekly report",
        ).id
        job = export_repo.create_job(
            s,
            tenant_id=tenant.id,
            item_id=app_item.id,
            user_id=owner.id,
            format="pdf",
        )  # left "pending" — not done, not error
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is None


def test_trigger_fails_report_without_deferring_when_export_capability_is_disabled(monkeypatch):
    # Revue finale SP-17b (I3) : un rapport créé pendant que la capacité
    # export était active reste en base si l'admin la coupe ensuite. Sans
    # garde, son rendu était déféré sur une file `export` que personne ne
    # dépile — job "pending" à jamais (reclaim_stuck_jobs ne récupère que les
    # "running"), et is_export_enabled() côté render_export_task ne s'exécute
    # jamais puisque rien ne dépile.
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    deferred = []
    monkeypatch.setattr(
        report_jobs,
        "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )

    report_jobs._trigger_due_reports(Session)

    assert deferred == []
    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None
        rows = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.run", AuditLog.object_id == report_id
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload["error"] == "export capability disabled on this instance"


def test_presigned_url_for_notification_uses_a_seven_day_ttl(monkeypatch):
    # Revue finale SP-17b (I4) : le défaut de generate_presigned_get_url est
    # 1 h — un lien envoyé par un cron nocturne ou de week-end était mort
    # avant d'être lu.
    captured = {}

    def _fake_presign(client, *, bucket, key, expires_in=3600):
        captured.update({"bucket": bucket, "key": key, "expires_in": expires_in})
        return "https://s3.test/presigned"

    monkeypatch.setattr(report_jobs, "generate_presigned_get_url", _fake_presign)
    monkeypatch.setattr(report_jobs, "s3_client_from_env", lambda: object())

    job = type("_Job", (), {"status": "done", "result_key": "renders/job-1.pdf"})()
    assert report_jobs._presigned_url_for_job(job) == "https://s3.test/presigned"
    assert captured["expires_in"] == 604_800


def test_presigned_url_is_none_for_a_job_that_is_not_done(monkeypatch):
    monkeypatch.setattr(
        report_jobs, "s3_client_from_env", lambda: pytest.fail("ne doit pas être appelé")
    )
    job = type("_Job", (), {"status": "error", "result_key": None})()
    assert report_jobs._presigned_url_for_job(job) is None


def test_notify_writes_a_notification_independently_of_configured_channels(monkeypatch):
    # NB (écart trouvé vs le texte du plan) : `ReportSchedulePayload` a son
    # propre validateur `_require_at_least_one_channel`
    # (app/configs/schemas.py, testé explicitement par
    # tests/test_report_config_schema.py::
    # test_report_schedule_payload_requires_at_least_one_channel) — un
    # `channels: []` ne peut PAS être persisté via
    # `BuilderConfig.model_validate`/`configs_repo.create_config` : la
    # validation lève immédiatement, et même en le forçant à l'écriture, la
    # relecture (`configs_repo.get_config_by_item` fait
    # `BuilderConfig.model_validate(revision.data)`) échouerait de la même
    # façon. Le scénario « channels vide » que ce test doit prouver
    # (indépendance de l'écriture de notification vis-à-vis de
    # `payload.channels`) est donc aujourd'hui inatteignable via la vraie API
    # de persistance — pas une erreur de cette tâche, un écart du texte du
    # plan/spec (qui affirme à tort que `payload.channels` "peut être vide")
    # contre le schéma réel. On exerce directement l'invariant de code visé
    # en contournant la persistance : `get_config_by_item` est monkeypatché
    # pour retourner un `ConfigRead` construit via `model_construct` (pas de
    # revalidation Pydantic déclenchée en passant une instance déjà du bon
    # type — vérifié empiriquement), portant `report.channels == []`. Le
    # reste du test (items/export/run réels) est inchangé.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard"
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report"
        ).id
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf"
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-2.pdf")
        reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()
        owner_id = owner.id

    from app.configs.repository import ConfigRead
    from app.configs.schemas import PipelineRefreshPolicy, ReportSchedulePayload

    no_channel_payload = ReportSchedulePayload.model_construct(
        bookmarkItemId="bookmark-x",
        refreshPolicy=PipelineRefreshPolicy(enabled=True, cron="*/5 * * * *"),
        channels=[],  # aucun canal configuré — la notification in-app doit tout de même s'écrire
    )
    no_channel_config = BuilderConfig.model_construct(kind="report", report=no_channel_payload)
    fake_config_read = ConfigRead(
        id="cfg-x", kind="report", itemId=report_id, version=1, config=no_channel_config
    )
    monkeypatch.setattr(
        configs_repo, "get_config_by_item", lambda session, item_id: fake_config_read
    )
    monkeypatch.setattr(
        report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-2.pdf"
    )
    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == owner_id
        assert notification.kind == "report"
        assert notification.status == "success"
        assert notification.item_resource_type == "report"
        assert notification.item_title == "Weekly report"


def test_trigger_failure_writes_a_failure_notification(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Broken report"
        ).id
        s.commit()
        owner_id = owner.id

    with Session() as s:
        report_jobs._record_trigger_failure(
            s,
            tenant_id=tenant.id,
            item_id=report_id,
            error="bookmark not readable",
            session_factory=Session,
        )
        s.commit()

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == owner_id
        assert notification.kind == "report"
        assert notification.status == "failure"
        assert notification.item_title == "Broken report"
        assert notification.error_message == "bookmark not readable"


def test_record_trigger_failure_survives_a_notification_write_that_poisons_its_own_session(
    monkeypatch,
):
    """Revue finale SP-39 (I1, falsification + I2) : create_notification est
    remplacé par une écriture qui viole une contrainte NOT NULL et fait
    échouer session.flush() (sous pytest's `filterwarnings=["error"]`, une
    SAWarning est promue en erreur avant le DB ; hors pytest, une
    IntegrityError au flush — le mécanisme ci-dessous qui empoisonne la
    session fonctionne identiquement dans les deux cas). Avant le correctif
    (l'écriture de notification partageait `session` avec le run+audit), un
    DBAPIError/SAWarning-as-error ici empoisonnait la transaction et faisait
    échouer le session.commit() qui suit, perdant le run+audit déjà en
    attente. Après le correctif (session isolée dans _notify), le run+audit
    survivent intacts, et le session.commit() de l'appelant ne lève jamais."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Broken report"
        ).id
        s.commit()
        tenant_id = tenant.id
        owner_id = owner.id

    def _boom(session, **kwargs):
        session.add(
            Notification(
                tenant_id=tenant_id,
                recipient_user_id=owner_id,
                kind="x",
                status="failure",
                item_title="x",
            )
        )  # id manquant (NOT NULL, pas de générateur) -> IntegrityError réel au flush()
        session.flush()

    monkeypatch.setattr(notifications_repo, "create_notification", _boom)

    with Session() as s:
        report_jobs._record_trigger_failure(
            s,
            tenant_id=tenant_id,
            item_id=report_id,
            error="bookmark not readable",
            session_factory=Session,
        )
        s.commit()  # ne doit jamais lever : jamais touchée par _boom (session isolée)

    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant_id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None
        assert run.notified_at is not None
        rows = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "report.run", AuditLog.object_id == report_id
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload["success"] is False
        # La notification elle-même n'a jamais été écrite (le boom l'en a
        # empêchée) — best-effort, mais le run+audit ci-dessus a bien survécu.
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant_id))
        assert notification is None


def test_notify_pending_reports_survives_a_notification_write_that_poisons_its_own_session(
    monkeypatch,
):
    """Second site du même I1 : _notify_pending_reports partageait aussi sa
    session entre l'écriture de notification et le mark_notified/commit du
    `finally`. Même falsification que le test ci-dessus (SAWarning-as-error
    sous pytest, IntegrityError hors), appliquée à ce second appelant."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard"
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report"
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf"
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-3.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()
        tenant_id = tenant.id
        owner_id = owner.id
        run_id = run.id

    def _boom(session, **kwargs):
        session.add(
            Notification(
                tenant_id=tenant_id,
                recipient_user_id=owner_id,
                kind="x",
                status="failure",
                item_title="x",
            )
        )
        session.flush()

    monkeypatch.setattr(notifications_repo, "create_notification", _boom)
    monkeypatch.setattr(report_jobs, "send_webhook", lambda channel, *, payload: None)
    monkeypatch.setattr(
        report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-3.pdf"
    )

    report_jobs._notify_pending_reports(Session)  # ne doit jamais lever

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant_id, run_id=run_id)
        # mark_notified/commit sur la session du sweep ont bien réussi : la
        # session isolée de _notify n'a jamais pu les empoisonner.
        assert fetched.notified_at is not None
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant_id))
        assert notification is None
