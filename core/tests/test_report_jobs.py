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
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None
        audit_rows = s.execute(
            select(AuditLog).where(AuditLog.action == "report.run", AuditLog.object_id == report_id)
        ).scalars().all()
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        # Bookmark détenu par "other", jamais partagé : le propriétaire du
        # rapport ne peut pas le lire → ReportTriggerError à chaque tentative.
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=other.id, app_id=app_item.id)
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        )
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": bookmark_id,
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * 1"},  # hebdomadaire
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        report_id = item.id
        s.commit()

    monkeypatch.setattr(
        report_jobs, "render_export_task", type("_T", (), {"defer": staticmethod(lambda **kw: None)}),
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        first_id = _seed_report(s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id)
        second_id = _seed_report(s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id)
        s.commit()

    attempts = []

    def _defer(**kw):
        attempts.append(kw)
        if len(attempts) == 1:
            raise Exception("procrastinate indisponible")

    monkeypatch.setattr(
        report_jobs, "render_export_task", type("_T", (), {"defer": staticmethod(_defer)}),
    )

    report_jobs._trigger_due_reports(Session)  # ne doit pas propager

    # Les DEUX rapports dus ont été traités : avant le correctif, l'exception
    # du premier remontait et le second n'était jamais atteint.
    assert len(attempts) == 2
    with Session() as s:
        failures = s.execute(
            select(AuditLog).where(AuditLog.action == "report.run", AuditLog.object_type == "item")
        ).scalars().all()
        assert len(failures) == 1
        assert failures[0].payload["success"] is False
        assert "mise en file impossible" in failures[0].payload["error"]
        assert failures[0].object_id in {first_id, second_id}
        # Le job du rapport en échec est clos en erreur : sans ça il resterait
        # "pending" pour toujours (personne ne l'a dépilé, et
        # reclaim_stuck_jobs ne récupère que les "running").
        failed_run = reports_repo.get_latest_run(
            s, tenant_id=tenant.id, report_item_id=failures[0].object_id,
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
    monkeypatch.setattr(
        report_jobs, "render_export_task",
        type("_T", (), {"defer": staticmethod(lambda **kw: deferred.append(kw))}),
    )

    def _boom(bookmark):
        raise ValueError("bookmark illisible")

    monkeypatch.setattr(report_jobs, "encode_analytics_context", _boom)

    report_jobs._trigger_due_reports(Session)  # ne doit pas propager

    assert deferred == []
    with Session() as s:
        rows = s.execute(
            select(AuditLog).where(AuditLog.action == "report.run", AuditLog.object_id == report_id)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].payload["success"] is False
        assert rows[0].payload["error"] == "erreur interne : bookmark illisible"


def test_notify_sends_webhook_with_result_url_and_marks_notified(monkeypatch):
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
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        ).id
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-x",
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id)
        s.commit()

    sent = []
    monkeypatch.setattr(report_jobs, "send_webhook", lambda channel, *, payload: sent.append((channel, payload)))
    monkeypatch.setattr(report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-1.pdf")
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        ).id
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-x",
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf",
        )
        export_repo.mark_error(s, job_id=job.id, error="worker crashed")
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id)
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        ).id
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-x",
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id)
        s.commit()

    def _boom(*a, **kw):
        raise RuntimeError("clé maître de secrets absente")

    monkeypatch.setattr(report_jobs, "send_webhook", _boom)
    monkeypatch.setattr(report_jobs, "_presigned_url_for_job", lambda job: None)

    report_jobs._notify_pending_reports(Session)  # ne doit pas propager

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None  # jamais rejoué, même sur erreur inattendue
        audit_rows = s.execute(
            select(AuditLog).where(AuditLog.action == "report.notify", AuditLog.object_id == report_id)
        ).scalars().all()
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        ).id
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-x",
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf",
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id)
        s.commit()

    sent = []
    monkeypatch.setattr(report_jobs, "send_webhook", lambda channel, *, payload: sent.append(payload))

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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report",
        ).id
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf",
        )  # left "pending" — not done, not error
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id)
        s.commit()

    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is None
