## Task 9: `app/reports/jobs.py` — trigger step

**Files:**
- Create: `core/app/reports/jobs.py`
- Test: `core/tests/test_report_jobs.py`

**Interfaces:**
- Consumes: `reports_repo.{create_run,list_due_reports}` (Task 7), `encode_analytics_context` (Task 8), `export_repo.create_job` (Task 3), `configs_repo.get_config_by_item`, `items_repo.get_access_facts`, `can`, `write_audit`.
- Produces: `_trigger_due_reports(session_factory) -> None`, `_owner_user(session, *, tenant_id, item_id) -> User`, both consumed by Task 10's `sweep_report_schedules_task`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_jobs.py
# SPDX-License-Identifier: Apache-2.0
"""_trigger_due_reports (SP-17b) — mirrors test_alert_jobs.py's shape for the
"resolve owner, re-check permissions, create export_jobs+report_runs" half of
the sweep. The notify half lives in test_report_jobs.py's sibling tests
below; the periodic-task-level commit-before-defer proof lives in
test_report_sweep.py (mirrors test_alert_sweep.py/test_pipeline_sweep.py)."""
from app.alerts.notify import NotifyError
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.items import repository as items_repo
from app.reports import jobs as report_jobs
from app.reports import repository as reports_repo
from app.sharing.authorization import can
from app.sharing.repository import share_item
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


def _seed_app(session, *, tenant_id, owner_id, item_id="app-1") -> None:
    # items_repo.create_item auto-assigns ids; force the exact "app-1" id the
    # bookmark above points at by writing the row directly through the same
    # repository helper other report tests already rely on (create_item does
    # NOT take an explicit id) — so seed the bookmark's appId AFTER creating
    # the app and read back its real id instead of hardcoding "app-1".
    pass  # placeholder not used — see test bodies below, which create the app first.


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
```

Note: `share_item` import above is unused if the two tests don't need it — drop the import if the final file doesn't reference it, to keep the test file lint-clean.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.jobs'`.

- [ ] **Step 3: Write `jobs.py` (trigger half only for this task)**

```python
# core/app/reports/jobs.py
# SPDX-License-Identifier: Apache-2.0
"""Procrastinate task for ReportSchedule (design SP-17b §2) — mirrors
app.alerts.jobs/app.pipelines.jobs exactly: a periodic sweep, two steps per
tick (trigger due schedules, then notify runs whose render finished),
commit-before-defer inside the per-item loop for the same reason as
run_pipeline_sweep_task. Permission is re-verified at trigger time against
the report's OWNER (not the schedule's creator, if those ever diverge —
mirrors app.alerts.jobs._owner_user): a report whose owner lost read access
to its bookmark/app fails cleanly (audited, no render) rather than either
crashing the sweep or silently rendering with elevated rights."""
import logging
import os

from sqlalchemy import select

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task
from app.items import repository as items_repo
from app.items.models import Item
from app.jobs import app
from app.reports import repository as reports_repo
from app.reports.ctx import encode_analytics_context
from app.sharing.authorization import can
from app.users.models import User

logger = logging.getLogger(__name__)


class ReportTriggerError(Exception):
    """Anything that keeps a due report from being rendered — always caught,
    always turns into an audit_log entry, never a crash of the sweep."""


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _owner_user(session, *, tenant_id: str, item_id: str) -> User:
    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise ReportTriggerError(f"report schedule '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _trigger_due_reports(session_factory) -> None:
    with request_scoped_session(session_factory) as session:
        due = reports_repo.list_due_reports(session)
        for item_id, tenant_id in due:
            try:
                config = configs_repo.get_config_by_item(session, item_id)
                if config is None or config.kind != "report":
                    continue
                payload = config.config.report
                assert payload is not None

                owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)

                bookmark_facts = items_repo.get_access_facts(
                    session, tenant_id=tenant_id, item_id=payload.bookmarkItemId,
                )
                if bookmark_facts is None or not can(session, user_id=owner.id, action="read", item=bookmark_facts):
                    raise ReportTriggerError("bookmark not readable by report owner")

                bookmark_config = configs_repo.get_config_by_item(session, payload.bookmarkItemId)
                if bookmark_config is None or bookmark_config.kind != "bookmark":
                    raise ReportTriggerError("bookmark config not found")
                bookmark = bookmark_config.config.bookmark
                assert bookmark is not None

                app_facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=bookmark.appId)
                if app_facts is None or not can(session, user_id=owner.id, action="read", item=app_facts):
                    raise ReportTriggerError("target app not readable by report owner")

                ctx = encode_analytics_context(bookmark)
                job = export_repo.create_job(
                    session, tenant_id=tenant_id, item_id=bookmark.appId, user_id=owner.id, format="pdf",
                    page_id=bookmark.pageId, ctx=ctx,
                )
                run = reports_repo.create_run(
                    session, tenant_id=tenant_id, report_item_id=item_id, export_job_id=job.id,
                )
                write_audit(
                    session, tenant_id=tenant_id, actor_id=owner.id, actor_kind="agent",
                    action="report.run", object_type="report_run", object_id=run.id,
                    payload={"reportItemId": item_id, "exportJobId": job.id, "success": True},
                )
                session.commit()
                render_export_task.defer(job_id=job.id, tenant_id=tenant_id)
            except ReportTriggerError as exc:
                logger.warning("report %s trigger failed: %s", item_id, exc)
                write_audit(
                    session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                    action="report.run", object_type="item", object_id=item_id,
                    payload={"success": False, "error": str(exc)},
                )
                session.commit()
        export_repo.reclaim_stuck_jobs(session)
        session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_jobs.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/jobs.py core/tests/test_report_jobs.py
git commit -m "feat(core): _trigger_due_reports — resolve owner, re-check access, create render (SP-17b)"
```

---

