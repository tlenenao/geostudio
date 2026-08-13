## Task 10: `app/reports/jobs.py` — notify step + periodic task

**Files:**
- Modify: `core/app/reports/jobs.py`
- Test: `core/tests/test_report_jobs.py` (extended), `core/tests/test_report_sweep.py` (new)

**Interfaces:**
- Consumes: `reports_repo.{list_unnotified_runs,mark_notified}` (Task 7), `export_repo.get_job` (existing), `send_webhook`/`send_email`/`NotifyError` (existing, `app.alerts.notify`).
- Produces: `sweep_report_schedules_task(timestamp: int) -> None` — the procrastinate periodic entrypoint, `@app.periodic(cron="*/5 * * * *")` / `@app.task(queue="etl")`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_report_jobs.py`:

```python
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
```

```python
# core/tests/test_report_sweep.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_jobs.py tests/test_report_sweep.py -v`
Expected: FAIL — `AttributeError: module 'app.reports.jobs' has no attribute '_notify_pending_reports'` (and `sweep_report_schedules_task`).

- [ ] **Step 3: Extend `jobs.py` with the notify step + periodic task**

Add these imports to the top of `core/app/reports/jobs.py`, alongside the existing ones:
```python
from app.alerts.notify import NotifyError, send_email, send_webhook
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.ingestion.storage import generate_presigned_get_url, make_s3_client
```

Append to the bottom of the file:

```python
def _s3_client_from_env():
    # Duplicated verbatim from app.export.jobs._s3_client_from_env (own
    # private helper, not imported — same "small helpers duplicated across
    # domain modules" convention as the commit-then-defer sequence itself).
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _presigned_url_for_job(job) -> str | None:
    if job.status != "done" or not job.result_key:
        return None
    bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    return generate_presigned_get_url(_s3_client_from_env(), bucket=bucket, key=job.result_key)


def _notify_pending_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        for run in reports_repo.list_unnotified_runs(session):
            job = export_repo.get_job(session, tenant_id=run.tenant_id, job_id=run.export_job_id)
            if job is None or job.status not in ("done", "error"):
                continue  # still rendering — revisit next tick

            report_config = configs_repo.get_config_by_item(session, run.report_item_id)
            if report_config is None or report_config.kind != "report":
                # Report item deleted after triggering — nothing left to
                # notify against; close the run out so the sweep doesn't
                # loop on it forever.
                reports_repo.mark_notified(session, run_id=run.id)
                session.commit()
                continue
            payload = report_config.config.report
            assert payload is not None

            item = items_repo.get_item(session, tenant_id=run.tenant_id, item_id=run.report_item_id)
            title = item.title if item is not None else run.report_item_id
            result_url = _presigned_url_for_job(job)
            message = (
                f"Rapport « {title} » : {job.status}."
                + (f" Lien : {result_url}" if result_url else "")
                + (f" Erreur : {job.error}" if job.error else "")
            )

            for channel in payload.channels:
                success = False
                error_detail = None
                try:
                    if isinstance(channel, AlertChannelWebhook):
                        send_webhook(
                            channel,
                            payload={"reportItemId": run.report_item_id, "status": job.status,
                                      "resultUrl": result_url, "error": job.error},
                        )
                    elif isinstance(channel, AlertChannelEmail):
                        send_email(
                            session, tenant_id=run.tenant_id, channel=channel,
                            subject=f"[GeoStudio] Rapport : {title}", body=message,
                        )
                    success = True
                except NotifyError as exc:
                    error_detail = str(exc)
                    logger.warning("report notification failed for run %s: %s", run.id, exc)
                write_audit(
                    session, tenant_id=run.tenant_id, actor_id=None, actor_kind="agent",
                    action="report.notify", object_type="item", object_id=run.report_item_id,
                    payload={"channel": channel.kind, "success": success, "error": error_detail},
                )

            # Posé après la tentative, quel que soit le résultat par canal —
            # une notification n'est jamais rejouée au tick suivant (design
            # SP-17b §2, cf. le risque documenté "webhook cassé de façon
            # permanente ne doit pas devenir un déni de service").
            reports_repo.mark_notified(session, run_id=run.id)
            session.commit()


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def sweep_report_schedules_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de rapports planifiés ignoré")
        return
    session_factory = _session_factory()
    _trigger_due_reports(session_factory)
    _notify_pending_reports(session_factory)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_jobs.py tests/test_report_sweep.py -v`
Expected: PASS (3 + 3 = 6 new tests, plus the 2 from Task 9 still passing).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/jobs.py core/tests/test_report_jobs.py core/tests/test_report_sweep.py
git commit -m "feat(core): sweep_report_schedules_task — notify step + periodic entrypoint (SP-17b)"
```

---

