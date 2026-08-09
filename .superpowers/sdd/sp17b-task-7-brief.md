## Task 7: `app/reports/repository.py`

**Files:**
- Create: `core/app/reports/repository.py`
- Test: `core/tests/test_report_repository.py`

**Interfaces:**
- Consumes: `ReportRun` (Task 6), `configs_repo.list_configs_by_kind` (existing, used cross-tenant like `list_due_pipelines`/`list_due_rules`).
- Produces: `create_run`, `get_run`, `list_runs`, `get_latest_run`, `list_unnotified_runs`, `mark_notified`, `list_due_reports` — consumed by Tasks 9-11.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_repository.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.repository'`.

- [ ] **Step 3: Write `repository.py`**

```python
# core/app/reports/repository.py
# SPDX-License-Identifier: Apache-2.0
"""Mirrors app.pipelines.repository (SP-15a/h) and app.alerts.repository
(SP-16b): "last run" is always derived from report_runs (never a duplicated
column on the config), list_due_reports reuses the same croniter-against-
last-created_at pattern as list_due_pipelines. Unlike ReportRun's sibling
tables, there is no "pending"/"running" status to reclaim here — a
report_runs row is only ever created immediately before its export_jobs row
is deferred (see app.reports.jobs), so there is no stuck-intermediate-state
window to guard against; a stuck render itself is already covered by
export_repo.reclaim_stuck_jobs (SP-17a)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.reports.models import ReportRun

import croniter


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, *, tenant_id: str, report_item_id: str, export_job_id: str) -> ReportRun:
    run = ReportRun(
        id=uuid.uuid4().hex, tenant_id=tenant_id,
        report_item_id=report_item_id, export_job_id=export_job_id,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def get_run(session: Session, *, tenant_id: str, run_id: str) -> ReportRun | None:
    return session.execute(
        select(ReportRun).where(ReportRun.id == run_id, ReportRun.tenant_id == tenant_id)
    ).scalar_one_or_none()


def list_runs(session: Session, *, tenant_id: str, report_item_id: str) -> list[ReportRun]:
    rows = session.execute(
        select(ReportRun)
        .where(ReportRun.tenant_id == tenant_id, ReportRun.report_item_id == report_item_id)
        .order_by(ReportRun.created_at.desc())
    ).scalars().all()
    return list(rows)


def get_latest_run(session: Session, *, tenant_id: str, report_item_id: str) -> ReportRun | None:
    return session.execute(
        select(ReportRun)
        .where(ReportRun.tenant_id == tenant_id, ReportRun.report_item_id == report_item_id)
        .order_by(ReportRun.created_at.desc())
        .limit(1)
    ).scalars().first()


def mark_notified(session: Session, *, run_id: str) -> None:
    run = session.get(ReportRun, run_id)
    if run is None:
        return
    run.notified_at = _now()
    session.flush()


def list_unnotified_runs(session: Session) -> list[ReportRun]:
    """Cross-tenant sweep, consumed by sweep_report_schedules_task's notify
    step — same discipline as list_due_reports below: never exposed via a
    route, the caller is a system task, not a user request."""
    rows = session.execute(
        select(ReportRun).where(ReportRun.notified_at.is_(None))
    ).scalars().all()
    return list(rows)


def list_due_reports(session: Session) -> list[tuple[str, str]]:
    """Cross-tenant sweep, consumed by sweep_report_schedules_task's trigger
    step. Never exposed via a route (same discipline as list_due_pipelines/
    list_due_rules): the tuple carries tenant_id in clear."""
    now = datetime.now(timezone.utc)
    due: list[tuple[str, str]] = []
    for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="report"):
        payload = config.report
        if payload is None:
            continue
        policy = payload.refreshPolicy
        if not policy.enabled:
            continue
        latest = get_latest_run(session, tenant_id=tenant_id, report_item_id=item_id)
        if latest is None:
            due.append((item_id, tenant_id))
            continue
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)
        if next_tick <= now:
            due.append((item_id, tenant_id))
    return due
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_repository.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/repository.py core/tests/test_report_repository.py
git commit -m "feat(core): app.reports.repository — runs CRUD + list_due_reports (SP-17b)"
```

---

