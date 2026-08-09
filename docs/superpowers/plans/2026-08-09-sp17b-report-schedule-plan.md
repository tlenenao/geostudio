# SP-17b — `ReportSchedule` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ReportSchedule` — a 9th `BuilderConfig` kind that renders a `Bookmark`'s frozen analytical state to PDF on a cron, via the existing SP-17a Playwright export worker, then notifies webhook/email channels (reused verbatim from SP-16b) with a presigned download link.

**Architecture:** A new `core/app/reports/` module (positioned above `app.alerts` in the layer contract) owns a `report_runs` table and a single periodic procrastinate task with two steps per tick — trigger due schedules (create an `export_jobs` row with new `page_id`/`ctx` columns, defer `render_export_task`) and notify runs whose joined export job reached `done`/`error`. `app.export` gains two nullable columns and a PDF footer template; nothing else in SP-17a changes. Shell adds a `ReportScheduleEditor` (mirrors `AlertRuleEditor`), a `ReportRunPanel` (mirrors `PipelineRunPanel`), a `ReportEditPage` (mirrors `PipelineBuilderPage`'s pk-nullable create/edit split), and one new entry point on bookmark rows.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic, Pydantic v2, procrastinate (queue `etl`), `croniter`; React + TanStack Query + React Router on the shell side.

## Global Constraints

- A `ReportSchedule` targets exactly **one `Bookmark`** (app + page + frozen context) — never a whole multi-page app. No PDF merging, no new dependency (`pypdf` etc.).
- Notification always carries a **presigned download link**, never a PDF attachment.
- Output format is **always PDF** — no PNG option, not configurable.
- Channels (`AlertChannel`, webhook/email) are the **exact `app.configs.schemas.AlertChannel` union reused verbatim** — no new "channel" abstraction.
- A notification is attempted **once per run, never retried** on the following tick, even on failure — this is deliberate (see spec §"Hors périmètre").
- `app.reports` must sit **above `app.alerts`** in `core/pyproject.toml`'s `[tool.importlinter]` layers (so it can import both `app.alerts.notify` and, transitively, `app.export`, which sits below `app.alerts`).
- Every new Alembic migration adds **nullable columns / new tables only** — no backfill, no destructive change.
- French comments/docstrings for anything narrating a non-obvious *why* (matches the rest of the codebase); code identifiers in English.

---

## File Structure

**Core — new files:**
- `core/app/reports/__init__.py` — empty module marker.
- `core/app/reports/models.py` — `ReportRun` SQLAlchemy model (table `report_runs`).
- `core/app/reports/repository.py` — CRUD + `list_due_reports` + `list_unnotified_runs`.
- `core/app/reports/ctx.py` — `encode_analytics_context(bookmark)`, a pure function producing the same base64url string shell's `encodeAnalyticsContext` would.
- `core/app/reports/jobs.py` — `sweep_report_schedules_task` (periodic, queue `etl`) + its two internal steps.
- `core/app/reports/routes.py` — `GET /reports/{item_id}/runs`.
- `core/app/configs/report_validation.py` — `validate_report_payload` (mirrors `alert_validation.py`).
- `core/alembic/versions/0022_export_jobs_page_ctx.py` — adds `export_jobs.page_id`/`export_jobs.ctx` (nullable).
- `core/alembic/versions/0023_report_runs.py` — creates `report_runs`.
- `core/tests/test_report_config_schema.py`, `test_report_validation.py`, `test_report_models.py`, `test_report_repository.py`, `test_report_ctx.py`, `test_report_jobs.py`, `test_report_sweep.py`, `test_report_routes.py`, `test_mcp_tools_report.py` — new test files.

**Core — modified files:**
- `core/app/configs/schemas.py` — add `ReportSchedulePayload`, extend `BuilderConfig.kind` Literal + `report` field + validator branch.
- `core/app/configs/routes.py` — wire `validate_report_payload` at all 3 mutating routes.
- `core/app/export/models.py` — add `page_id`, `ctx` nullable columns to `ExportJob`.
- `core/app/export/repository.py` — `create_job` gains optional `page_id`/`ctx` params.
- `core/app/export/jobs.py` — `render_export_task` appends `/{page_id}` and `&ctx=` when set.
- `core/app/export/rendering.py` — `RenderPage.pdf` Protocol + `render_export` gain a PDF footer template.
- `core/app/jobs.py` — add `"app.reports.jobs"` to `import_paths`.
- `core/app/main.py` — mount `app.reports.routes.router` (unconditional, like `alerts_routes`).
- `core/pyproject.toml` — insert `"app.reports"` layer + `ignore_imports` entry.
- `core/app/mcp/tools.py` — add `explain_report_schedule` tool.
- `core/tests/test_export_repository.py`, `test_export_jobs.py`, `test_export_rendering.py` — extended, not replaced.

**Shell — new files:**
- `shell/src/builder/report/ReportScheduleEditor.tsx` — inline create form (mirrors `AlertRuleEditor.tsx`).
- `shell/src/builder/report/ReportRunPanel.tsx` — run history poll panel (mirrors `PipelineRunPanel.tsx`, no "Exécuter" button — reports are sweep-triggered only).
- `shell/src/pages/ReportEditPage.tsx` — create/edit page (mirrors `PipelineBuilderPage.tsx`'s `pk: string | null` split).
- `shell/e2e/report-schedule.spec.ts` — new E2E spec.

**Shell — modified files:**
- `shell/src/api/types.ts` — add `"report"` to `ResourceType`; add `ReportSchedulePayload`, `ReportRunStatus` types.
- `shell/src/api/itemClient.ts` — add `createReportScheduleItem`, `getReportScheduleConfig`, `saveReportScheduleConfig`, `getReportRuns`.
- `shell/src/api/hooks.ts` — add `useCreateReportSchedule`, `useReportScheduleConfig`, `useSaveReportSchedule`.
- `shell/src/shell/routes.tsx` — `/reports`, `/reports/new`, `/reports/:pk/edit` routes; `useOpenItem`'s `"report"` branch.
- `shell/src/shell/ItemActions.tsx` — "Programmer un rapport" menu entry, shown only for `resourceType === "bookmark"`.

---

## Task 1: `ReportSchedulePayload` schema + `BuilderConfig` kind registration

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_report_config_schema.py`

**Interfaces:**
- Produces: `ReportSchedulePayload(bookmarkItemId: str, refreshPolicy: PipelineRefreshPolicy, channels: list[AlertChannel])`, consumed by every later core task.
- Produces: `BuilderConfig.kind` now accepts `"report"`, and `BuilderConfig.report: ReportSchedulePayload | None`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_config_schema.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig, ReportSchedulePayload


def _payload(**overrides) -> dict:
    base = {
        "bookmarkItemId": "bookmark-1",
        "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
        "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
    }
    base.update(overrides)
    return base


def test_report_schedule_payload_round_trips():
    payload = ReportSchedulePayload.model_validate(_payload())
    assert payload.bookmarkItemId == "bookmark-1"
    assert payload.refreshPolicy.cron == "0 8 * * MON"
    assert payload.channels[0].kind == "webhook"


def test_report_schedule_payload_requires_at_least_one_channel():
    with pytest.raises(ValidationError, match="at least one channel"):
        ReportSchedulePayload.model_validate(_payload(channels=[]))


def test_report_schedule_payload_rejects_invalid_cron():
    with pytest.raises(ValidationError):
        ReportSchedulePayload.model_validate(_payload(refreshPolicy={"enabled": True, "cron": "not-a-cron"}))


def test_builder_config_accepts_kind_report():
    config = BuilderConfig.model_validate({"kind": "report", "report": _payload()})
    assert config.kind == "report"
    assert config.report is not None
    assert config.report.bookmarkItemId == "bookmark-1"


def test_builder_config_kind_report_requires_report_payload():
    with pytest.raises(ValidationError, match="report config requires"):
        BuilderConfig.model_validate({"kind": "report"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_config_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReportSchedulePayload'`.

- [ ] **Step 3: Add `ReportSchedulePayload` and register the `"report"` kind**

In `core/app/configs/schemas.py`, immediately after the existing `AlertRulePayload` class (the one ending with its `_require_single_scalar_query` validator), add:

```python
class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    refreshPolicy: PipelineRefreshPolicy  # reused verbatim, same shape as pipeline/alert scheduling
    channels: list[AlertChannel] = Field(default_factory=list)  # reused verbatim from AlertRule (SP-16b)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self
```

Then in `BuilderConfig`, change:

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert"]
```
to:
```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert", "report"]
```

Add the field, right after `alert: AlertRulePayload | None = None`:
```python
    alert: AlertRulePayload | None = None
    report: ReportSchedulePayload | None = None
```

And in `_require_kind_payload`, right after the `"alert"` branch:
```python
        if self.kind == "alert" and self.alert is None:
            raise ValueError("alert config requires an alert payload")
        if self.kind == "report" and self.report is None:
            raise ValueError("report config requires a report payload")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_config_schema.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/configs/schemas.py core/tests/test_report_config_schema.py
git commit -m "feat(core): ReportSchedulePayload schema, 9th BuilderConfig kind (SP-17b)"
```

---

## Task 2: `validate_report_payload` + wiring into `/configs` routes

**Files:**
- Create: `core/app/configs/report_validation.py`
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_report_validation.py`

**Interfaces:**
- Consumes: `BuilderConfig`, `ReportSchedulePayload` (Task 1); `items_repo.get_access_facts`/`get_item`, `can` (existing).
- Produces: `validate_report_payload(session, config, *, user) -> None` (raises `HTTPException(422)` on an unreadable/wrong-type bookmark), called at `POST /configs`, `PUT /configs/{id}`, `PUT /configs/by-item/{id}`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_validation.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.configs.report_validation import validate_report_payload
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _report_config(bookmark_item_id: str) -> BuilderConfig:
    return BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": bookmark_item_id,
            "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })


def test_ignores_non_report_kind():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        config = BuilderConfig.model_validate({"kind": "pipeline", "pipeline": {"nodes": [], "edges": []}})
        validate_report_payload(s, config, user=user)  # no raise


def test_rejects_unreadable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        config = _report_config("does-not-exist")
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_rejects_bookmark_item_id_pointing_at_non_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Not a bookmark",
        )
        s.commit()
        config = _report_config(item.id)
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_accepts_readable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="bookmark", title="A view",
        )
        s.commit()
        config = _report_config(item.id)
        validate_report_payload(s, config, user=user)  # no raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.configs.report_validation'`.

- [ ] **Step 3: Write `report_validation.py`**

```python
# core/app/configs/report_validation.py
# SPDX-License-Identifier: Apache-2.0
"""Direct kind="report" validation for app.configs. Mirrors
app.configs.alert_validation/bookmark_validation exactly: bookmarkItemId
always refers to an item of resourceType "bookmark", and app.configs already
imports app.items, so there is no forbidden cross-module dependency to route
around (SP-17b design §Modèle de données)."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_report_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "report":
        return
    payload = config.report
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak bookmark
        # existence, same convention as app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="bookmark not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "bookmark":
        raise HTTPException(status_code=422, detail="bookmark not found")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_validation.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire into `core/app/configs/routes.py`**

Add the import next to the other `_validate_*_payload` imports:
```python
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
from app.configs.report_validation import validate_report_payload as _validate_report_payload
```

Add one call right after every existing `_validate_alert_payload(...)` line — three call sites:

`create_config` (after `_validate_alert_payload(session, request.config, user=user)`):
```python
    _validate_alert_payload(session, request.config, user=user)
    _validate_report_payload(session, request.config, user=user)
```

`update_config` (after `_validate_alert_payload(session, config, user=user)`):
```python
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
```

`update_config_by_item` (after `_validate_alert_payload(session, config, user=user)`):
```python
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
```

- [ ] **Step 6: Run the full configs test suite**

Run: `cd core && uv run pytest tests/test_configs_routes.py tests/test_alert_routes.py -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/configs/report_validation.py core/app/configs/routes.py core/tests/test_report_validation.py
git commit -m "feat(core): validate ReportSchedule.bookmarkItemId on /configs writes (SP-17b)"
```

---

## Task 3: `ExportJob.page_id`/`ctx` columns + repository + migration

**Files:**
- Modify: `core/app/export/models.py`
- Modify: `core/app/export/repository.py`
- Create: `core/alembic/versions/0022_export_jobs_page_ctx.py`
- Test: `core/tests/test_export_repository.py` (extended)

**Interfaces:**
- Produces: `ExportJob.page_id: str | None`, `ExportJob.ctx: str | None`.
- Produces: `export_repo.create_job(session, *, tenant_id, item_id, user_id, format, page_id=None, ctx=None) -> ExportJob`.

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_export_repository.py` (new test, existing tests in that file stay untouched):

```python
def test_create_job_accepts_optional_page_id_and_ctx():
    Session = _make_session()  # existing helper in this file
    with Session() as s:
        tenant, user, item_id = _seed(s)  # existing helper in this file
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=item_id, user_id=user.id, format="pdf",
            page_id="page-2", ctx="eyJ0aW1lUmFuZ2UiOm51bGx9",
        )
        assert job.page_id == "page-2"
        assert job.ctx == "eyJ0aW1lUmFuZ2UiOm51bGx9"


def test_create_job_defaults_page_id_and_ctx_to_none():
    Session = _make_session()
    with Session() as s:
        tenant, user, item_id = _seed(s)
        job = export_repo.create_job(s, tenant_id=tenant.id, item_id=item_id, user_id=user.id, format="png")
        assert job.page_id is None
        assert job.ctx is None
```

If `_make_session`/`_seed` helpers don't already exist under those exact names in `test_export_repository.py`, read the file first and reuse whatever the existing tests already call (do not introduce a second seeding helper).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_repository.py -k page_id -v`
Expected: FAIL — `TypeError: create_job() got an unexpected keyword argument 'page_id'`.

- [ ] **Step 3: Add the columns**

In `core/app/export/models.py`, add two nullable columns to `ExportJob`, right after `format`:

```python
    format: Mapped[str] = mapped_column(String, nullable=False)
    # Nullable, additive (SP-17b) : None préserve le comportement actuel du
    # bouton d'export manuel (pas de page/contexte particulier) ; renseignés
    # uniquement par le sweep de app.reports.jobs.
    page_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ctx: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
```

- [ ] **Step 4: Extend `create_job`**

In `core/app/export/repository.py`:

```python
def create_job(
    session: Session, *, tenant_id: str, item_id: str, user_id: str, format: str,
    page_id: str | None = None, ctx: str | None = None,
) -> ExportJob:
    job = ExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        format=format, status="pending", page_id=page_id, ctx=ctx,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job
```

- [ ] **Step 5: Write the migration**

```python
# core/alembic/versions/0022_export_jobs_page_ctx.py
# SPDX-License-Identifier: Apache-2.0
"""app.export — export_jobs.page_id / export_jobs.ctx (SP-17b)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("page_id", sa.String(), nullable=True))
    op.add_column("export_jobs", sa.Column("ctx", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "ctx")
    op.drop_column("export_jobs", "page_id")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_export_repository.py tests/test_export_jobs.py tests/test_export_routes.py -v`
Expected: PASS, no regressions in the existing export suite.

- [ ] **Step 7: Verify the migration against a real Postgres**

The `pg_engine` pytest fixture (`core/tests/conftest.py`) builds its schema via `Base.metadata.create_all()`, never `alembic upgrade head` — so this migration is not exercised by any automated test and must be checked by hand (this is the exact gap SP-17a's `export_jobs` migration fell into in round 1 of its final review). With the dev stack's Postgres running (`docker compose up -d postgis` from the repo root, or point `DATABASE_URL` at any real Postgres):

```bash
cd core
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic upgrade head
```
Expected: no error, ends at `0022 (head)`.

```bash
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic downgrade -1
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic upgrade head
```
Expected: downgrade drops both columns without error, re-upgrade succeeds. Adjust the connection string to whatever `DATABASE_URL` your local `.env`/`docker-compose.yml` actually uses if different.

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/export/models.py core/app/export/repository.py core/alembic/versions/0022_export_jobs_page_ctx.py core/tests/test_export_repository.py
git commit -m "feat(core): export_jobs.page_id/ctx columns for report renders (SP-17b)"
```

---

## Task 4: `render_export_task` builds the URL with `page_id`/`ctx`

**Files:**
- Modify: `core/app/export/jobs.py`
- Test: `core/tests/test_export_jobs.py` (extended)

**Interfaces:**
- Consumes: `ExportJob.page_id`/`ctx` (Task 3).
- Produces: no signature change — `render_export_task(job_id, tenant_id)` behavior only.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_export_jobs.py` first to find its existing fixture for asserting the navigated URL (it monkeypatches `_launch_and_navigate` — reuse that exact pattern). Add:

```python
def test_render_export_task_builds_url_with_page_id_and_ctx(monkeypatch, ...):  # reuse this file's existing fixture args
    captured_urls = []

    def fake_launch_and_navigate(url):
        captured_urls.append(url)
        return _FakePage()  # reuse this file's existing fake page helper

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", fake_launch_and_navigate)
    # ... reuse this file's existing setup to create a job, but pass page_id/ctx:
    job = export_repo.create_job(
        session, tenant_id=tenant_id, item_id=item_id, user_id=user_id, format="pdf",
        page_id="page-2", ctx="abc123",
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant_id)

    assert len(captured_urls) == 1
    assert f"/apps/{item_id}/page-2?exportToken=" in captured_urls[0]
    assert captured_urls[0].endswith("&ctx=abc123")


def test_render_export_task_url_unchanged_when_page_id_and_ctx_absent(monkeypatch, ...):
    captured_urls = []
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: captured_urls.append(url) or _FakePage())
    job = export_repo.create_job(session, tenant_id=tenant_id, item_id=item_id, user_id=user_id, format="pdf")
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant_id)

    assert f"/apps/{item_id}?exportToken=" in captured_urls[0]
    assert "ctx=" not in captured_urls[0]
```

Adapt variable names (`session`, `tenant_id`, `item_id`, `user_id`, `_FakePage`) to whatever this file's existing tests actually call — do not invent new fixture names that collide with the file's conventions.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_jobs.py -k page_id -v`
Expected: FAIL — URL has no `/page-2` segment or `&ctx=`.

- [ ] **Step 3: Extend `render_export_task`**

In `core/app/export/jobs.py`, the job-fetch block currently reads:
```python
        job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        export_repo.mark_running(session, job_id=job_id)
        item_id, user_id, export_format = job.item_id, job.user_id, job.format
```
Change the last line to also capture the two new columns:
```python
        item_id, user_id, export_format = job.item_id, job.user_id, job.format
        page_id, ctx = job.page_id, job.ctx
```

And the URL-building block:
```python
        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        target_url = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}?exportToken={token}&exportRender=1"
```
becomes:
```python
        from urllib.parse import quote

        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        base = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}"
        if page_id:
            base = f"{base}/{quote(page_id, safe='')}"
        target_url = f"{base}?exportToken={token}&exportRender=1"
        if ctx:
            target_url = f"{target_url}&ctx={ctx}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: PASS, including the two new tests and all pre-existing ones.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/export/jobs.py core/tests/test_export_jobs.py
git commit -m "feat(core): render_export_task navigates to page_id/ctx when set (SP-17b)"
```

---

## Task 5: PDF footer template (generation date) on every export

**Files:**
- Modify: `core/app/export/rendering.py`
- Test: `core/tests/test_export_rendering.py` (extended)

**Interfaces:**
- Produces: `render_export(page, *, format, print_layout)` now calls `page.pdf(..., display_header_footer=True, footer_template=...)`. `RenderPage.pdf` Protocol signature grows two required kwargs.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_export_rendering.py` first for its existing fake-page fixture (it will need a `pdf(self, **kwargs)` that records kwargs — reuse it, extending its recorded-kwargs assertion). Add:

```python
def test_render_export_pdf_sets_display_header_footer_with_generation_date_template():
    page = _FakePage()  # reuse this file's existing fake
    render_export(page, format="pdf", print_layout=None)

    assert page.pdf_kwargs["display_header_footer"] is True
    assert "Généré le" in page.pdf_kwargs["footer_template"]
    assert '<span class="date">' in page.pdf_kwargs["footer_template"]
```

If the existing fake page's `pdf()` doesn't record its kwargs on a `pdf_kwargs` attribute already, extend the fake in this file to do so — check what the pre-existing `test_render_export_*` tests already assert against before renaming anything.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_rendering.py -k footer -v`
Expected: FAIL — `KeyError: 'display_header_footer'` or similar.

- [ ] **Step 3: Update `RenderPage` and `render_export`**

```python
# core/app/export/rendering.py
class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(
        self, *, format: str, landscape: bool, print_background: bool,
        display_header_footer: bool, footer_template: str,
    ) -> bytes: ...


_FOOTER_TEMPLATE = (
    '<div style="font-size:8px; width:100%; text-align:center; color:#666;">'
    'Généré le <span class="date"></span></div>'
)


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(
        format=layout.pageSize.upper(), landscape=layout.orientation == "landscape", print_background=True,
        # display_header_footer/footer_template (SP-17b) : seul morceau
        # d'"en-tête/pied" retenu dans le périmètre resserré du design — pas
        # de numérotation de section, une seule page source par export.
        # <span class="date"> est une classe Chromium native, remplie
        # automatiquement à la date du rendu — rien à calculer côté Python.
        display_header_footer=True, footer_template=_FOOTER_TEMPLATE,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/export/rendering.py core/tests/test_export_rendering.py
git commit -m "feat(core): PDF exports get a generation-date footer (SP-17b)"
```

---

## Task 6: `ReportRun` model + migration

**Files:**
- Create: `core/app/reports/__init__.py`
- Create: `core/app/reports/models.py`
- Create: `core/alembic/versions/0023_report_runs.py`
- Test: `core/tests/test_report_models.py`

**Interfaces:**
- Produces: `ReportRun(id, tenant_id, report_item_id, export_job_id, notified_at, created_at)`.

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_report_models.py
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports.models import ReportRun
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
import uuid


def test_report_run_persists_and_defaults_notified_at_to_none():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        report_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="report", title="Weekly report",
        )
        s.commit()

        run = ReportRun(
            id=uuid.uuid4().hex, tenant_id=tenant.id,
            report_item_id=report_item.id, export_job_id="job-1",
        )
        s.add(run)
        s.commit()
        s.refresh(run)

        assert run.notified_at is None
        assert run.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_report_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports'`.

- [ ] **Step 3: Create the module and model**

```python
# core/app/reports/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/reports/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    report_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    # Pas de FK SQL vers export_jobs.id : app.export sits below app.reports
    # in the layer contract but export_jobs rows are looked up by id through
    # export_repo.get_job at read time (§2 of the design), never joined in
    # SQL — même discipline que pipeline_runs/get_latest_run.
    export_job_id: Mapped[str] = mapped_column(String, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_report_models.py -v`
Expected: PASS.

- [ ] **Step 5: Write the migration**

```python
# core/alembic/versions/0023_report_runs.py
# SPDX-License-Identifier: Apache-2.0
"""app.reports — report_runs (SP-17b)

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("report_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("export_job_id", sa.String(), nullable=False),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_report_runs_tenant_id", "report_runs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_report_runs_tenant_id", table_name="report_runs")
    op.drop_table("report_runs")
```

- [ ] **Step 6: Verify the migration against a real Postgres**

```bash
cd core
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic upgrade head
```
Expected: no error, ends at `0023 (head)`. Adjust the connection string to your actual local `DATABASE_URL` if different (see Task 3 Step 7 for the same caveat).

```bash
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic downgrade -1
DATABASE_URL=postgresql+psycopg://geostudio:geostudio@localhost:5432/geostudio_dev uv run alembic upgrade head
```
Expected: clean round-trip.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/__init__.py core/app/reports/models.py core/alembic/versions/0023_report_runs.py core/tests/test_report_models.py
git commit -m "feat(core): report_runs table (SP-17b)"
```

---

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

## Task 8: `encode_analytics_context`

**Files:**
- Create: `core/app/reports/ctx.py`
- Test: `core/tests/test_report_ctx.py`

**Interfaces:**
- Consumes: `BookmarkPayload` (existing, `core/app/configs/schemas.py`).
- Produces: `encode_analytics_context(bookmark: BookmarkPayload) -> str`, consumed by Task 9.

This must produce the same base64url string shell's `shell/src/lib/analyticsContextUrl.ts::encodeAnalyticsContext` would produce for the equivalent `{timeRange, extent, crossFilter}` state, since `AppRuntimePage` decodes it with `decodeAnalyticsContext` (base64url → JSON, `{timeRange, extent, crossFilter}`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_ctx.py
# SPDX-License-Identifier: Apache-2.0
import base64
import json

from app.configs.schemas import BookmarkPayload
from app.reports.ctx import encode_analytics_context


def _decode(raw: str) -> dict:
    # Mirrors shell/src/lib/analyticsContextUrl.ts::decodeAnalyticsContext's
    # base64url handling exactly (- -> +, _ -> /, re-pad to a multiple of 4).
    padded = raw.replace("-", "+").replace("_", "/")
    padded += "=" * ((4 - len(padded) % 4) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


def test_encode_round_trips_full_context():
    bookmark = BookmarkPayload.model_validate({
        "appId": "app-1", "pageId": "page-1",
        "timeRange": {"from": "2026-01-01", "to": "2026-12-31"},
        "extent": [1.0, 2.0, 3.0, 4.0],
        "crossFilter": {
            "dataset-1": {"field": "score", "value": {"from": "10", "to": "90"}, "originSourceId": "src-1"},
        },
    })

    encoded = encode_analytics_context(bookmark)
    decoded = _decode(encoded)

    assert decoded["timeRange"] == {"from": "2026-01-01", "to": "2026-12-31"}
    assert decoded["extent"] == [1.0, 2.0, 3.0, 4.0]
    assert decoded["crossFilter"] == {
        "dataset-1": {"field": "score", "value": {"from": "10", "to": "90"}, "originSourceId": "src-1"},
    }


def test_encode_handles_empty_context():
    bookmark = BookmarkPayload.model_validate({"appId": "app-1", "pageId": "page-1"})

    decoded = _decode(encode_analytics_context(bookmark))

    assert decoded == {"timeRange": None, "extent": None, "crossFilter": {}}


def test_encode_is_url_safe():
    bookmark = BookmarkPayload.model_validate({
        "appId": "app-1", "pageId": "page-1",
        "crossFilter": {"f": {"field": "libellé", "value": ["a", "b", "c???/+++"], "originSourceId": "s"}},
    })

    encoded = encode_analytics_context(bookmark)

    assert "+" not in encoded
    assert "/" not in encoded
    assert "=" not in encoded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_ctx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.ctx'`.

- [ ] **Step 3: Write `ctx.py`**

```python
# core/app/reports/ctx.py
# SPDX-License-Identifier: Apache-2.0
"""Mirrors shell/src/lib/analyticsContextUrl.ts::encodeAnalyticsContext byte
for byte: base64url (RFC 4648 §5) of the UTF-8 JSON encoding of
{timeRange, extent, crossFilter} — the exact three fields AppRuntimePage's
decodeAnalyticsContext reads back out of ?ctx=. Kept as its own tiny module
(not inlined in jobs.py) so it can be unit-tested against the JS
implementation's exact wire format without needing a running sweep."""
import base64
import json

from app.configs.schemas import BookmarkPayload


def encode_analytics_context(bookmark: BookmarkPayload) -> str:
    state = {
        "timeRange": bookmark.timeRange.model_dump(by_alias=True) if bookmark.timeRange else None,
        "extent": list(bookmark.extent) if bookmark.extent else None,
        "crossFilter": {key: entry.model_dump() for key, entry in bookmark.crossFilter.items()},
    }
    json_bytes = json.dumps(state).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_ctx.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/ctx.py core/tests/test_report_ctx.py
git commit -m "feat(core): encode_analytics_context mirrors shell's ?ctx= wire format (SP-17b)"
```

---

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

## Task 11: `GET /reports/{item_id}/runs`

**Files:**
- Create: `core/app/reports/routes.py`
- Test: `core/tests/test_report_routes.py`

**Interfaces:**
- Consumes: `reports_repo.list_runs` (Task 7), `export_repo.get_job` (existing), `generate_presigned_get_url` (existing).
- Produces: `router: APIRouter` with `GET /reports/{item_id}/runs -> list[ReportRunStatus]`, mounted in Task 12.

- [ ] **Step 1: Write the failing tests**

Read `core/tests/test_alert_routes.py` and `core/tests/test_export_routes.py` first for this codebase's FastAPI `TestClient` + auth-override fixture conventions, then mirror them exactly:

```python
# core/tests/test_report_routes.py
# SPDX-License-Identifier: Apache-2.0
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import get_session, init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.ingestion.routes import get_s3_client
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.reports.routes import get_exports_bucket, router
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3:
    def generate_presigned_url(self, *a, **kw):
        return "https://s3.test/presigned"


def _make_app_and_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = FastAPI()
    app.include_router(router)

    def _get_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_s3_client] = lambda: _FakeS3()
    app.dependency_overrides[get_exports_bucket] = lambda: "geostudio-exports"
    return app, Session


def _seed(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    app_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Dashboard",
    )
    report_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="report", title="Weekly report",
    )
    config = BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": "bookmark-x",
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })
    configs_repo.create_config(session, config, item_id=report_item.id, tenant_id=tenant.id)
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=app_item.id, user_id=user.id, format="pdf")
    export_repo.mark_done(session, job_id=job.id, result_key="renders/job-1.pdf")
    run = reports_repo.create_run(session, tenant_id=tenant.id, report_item_id=report_item.id, export_job_id=job.id)
    session.commit()
    return tenant, user, report_item.id, run.id


def test_get_report_runs_returns_run_with_resolved_status_and_url():
    app, Session = _make_app_and_session()
    with Session() as s:
        tenant, user, report_id, run_id = _seed(s)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    response = client.get(f"/reports/{report_id}/runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == run_id
    assert body[0]["status"] == "done"
    assert body[0]["resultUrl"] == "https://s3.test/presigned"


def test_get_report_runs_404s_for_unreadable_report():
    app, Session = _make_app_and_session()
    with Session() as s:
        tenant, user, report_id, run_id = _seed(s)
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
    app.dependency_overrides[get_current_user] = lambda: other
    client = TestClient(app)

    response = client.get(f"/reports/{report_id}/runs")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.routes'`.

- [ ] **Step 3: Write `routes.py`**

```python
# core/app/reports/routes.py
# SPDX-License-Identifier: Apache-2.0
"""REST routes for ReportSchedule (SP-17b §3) — CRUD itself is entirely the
generic /configs routes (kind="report"), like AlertRule/Pipeline; this module
only carries the one bespoke read, mirroring GET /alerts/{id}/evaluations."""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.export import repository as export_repo
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


class ReportRunStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None
    notifiedAt: str | None
    createdAt: str


def get_exports_bucket() -> str:
    # Même clé de dependency-override qu'app.export.routes — réutilisée par
    # nom (pas importée) pour que app.main puisse overrider les deux
    # indépendamment sans qu'un des deux modules importe l'autre pour rien.
    return os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")


def _require_report_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="report schedule not found")


@router.get("/reports/{item_id}/runs", response_model=list[ReportRunStatus])
def get_report_runs_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_exports_bucket),
) -> list[ReportRunStatus]:
    _require_report_read_access(session, user=user, item_id=item_id)
    runs = reports_repo.list_runs(session, tenant_id=user.tenant_id, report_item_id=item_id)
    result: list[ReportRunStatus] = []
    for run in runs:
        job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=run.export_job_id)
        status = job.status if job is not None else "unknown"
        result_url = None
        if job is not None and job.status == "done" and job.result_key:
            result_url = generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)
        result.append(ReportRunStatus(
            id=run.id, status=status, resultUrl=result_url,
            error=job.error if job is not None else None,
            notifiedAt=run.notified_at.isoformat() if run.notified_at else None,
            createdAt=run.created_at.isoformat(),
        ))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_routes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/routes.py core/tests/test_report_routes.py
git commit -m "feat(core): GET /reports/{item_id}/runs (SP-17b)"
```

---

## Task 12: Wire `app.reports` into the worker, the API app, and the layer contract

**Files:**
- Modify: `core/app/jobs.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml`
- Test: none new — this task is pure wiring, verified by the full suite + `lint-imports`.

**Interfaces:**
- No new interfaces; this task makes Tasks 6-11's code reachable at runtime (procrastinate worker, FastAPI app) and satisfies the import-linter contract.

- [ ] **Step 1: Register the periodic task with the worker**

In `core/app/jobs.py`, add `"app.reports.jobs"` to `import_paths`:

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs", "app.reports.jobs",
    ],
```

- [ ] **Step 2: Mount the reports router**

In `core/app/main.py`, add the import next to the other domain route imports:
```python
from app.public import routes as public_routes
from app.reports import routes as reports_routes
from app.secrets import crypto as secrets_crypto
```

And mount it unconditionally, right after `alerts_routes` (no capability flag — mirrors `alerts_routes`, not `pipelines_routes`/`export_routes`; a `ReportSchedule` can be created/listed/inspected even with `CORE_EXPORT_ENABLED=false`, it just fails cleanly at render time per the design's §5):
```python
    app.include_router(alerts_routes.router)
    app.include_router(reports_routes.router)
    if is_etl_enabled():
```

- [ ] **Step 3: Insert `app.reports` into the import-linter layer contract**

In `core/pyproject.toml`, in the `layers` list, insert `"app.reports",` between `"app.pipelines",` and `"app.alerts",`:

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.reports",
    "app.alerts",
    "app.export",
    "app.secrets",
    ...
```

And add a matching `ignore_imports` entry, next to the existing `app.db -> app.export.models` line (same reason as every other domain-models exception in that list — `app.db` is intentionally outside the layer contract, see the comment on `core/app/jobs.py`):
```toml
    "app.db -> app.export.models",
    "app.db -> app.reports.models",
]
```

- [ ] **Step 4: Verify the layer contract holds**

Run: `cd core && uv run lint-imports`
Expected: no violation reported (in particular, no complaint about `app.reports` importing `app.alerts.notify`/`app.export.repository`/`app.export.jobs`/`app.configs`/`app.items`/`app.sharing`/`app.audit`/`app.users`/`app.db`).

If `lint-imports` is not directly on PATH, run it via `uv run python -m importlinter`.

- [ ] **Step 5: Run the worker-registration test**

Run: `cd core && uv run pytest tests/test_jobs.py -v`
Expected: PASS — in particular `test_import_paths_registers_all_domain_tasks` (or equivalent) should now also see `sweep_report_schedules_task` registered.

- [ ] **Step 6: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: PASS (previous count + all new SP-17b tests), no regressions. `postgis`-marked tests will skip unless `CORE_TEST_DATABASE_URL` is set — that's expected locally.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/jobs.py core/app/main.py core/pyproject.toml
git commit -m "feat(core): wire app.reports into worker/app/import-linter contract (SP-17b)"
```

---

## Task 13: MCP `explain_report_schedule`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_report.py`

**Interfaces:**
- Consumes: `reports_repo.get_latest_run` (Task 7), `configs_repo`, `items_repo`, `can` (existing, already imported in `tools.py`).
- Produces: MCP tool `explain_report_schedule(reportScheduleId: str) -> dict`, registered unconditionally.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_mcp_tools_alert.py` first for this file's exact `register_tools`/fake-`Context` test-harness pattern, then mirror it:

```python
# core/tests/test_mcp_tools_report.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# Reuse this test file's own imports/fixtures for register_tools/FastMCP/
# fake Context/_resolve_actor monkeypatching — copy the exact harness from
# test_mcp_tools_alert.py (server, session_factory, fake ctx with a token)
# rather than re-deriving it here.


@pytest.mark.asyncio
async def test_explain_report_schedule_returns_bookmark_schedule_and_channels(mcp_server_and_session):  # fixture name from the copied harness
    server, session_factory, ctx = mcp_server_and_session
    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="report", title="Weekly report",
        )
        config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-1",
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        run = reports_repo.create_run(s, tenant_id=tenant.id, report_item_id=item.id, export_job_id="job-1")
        s.commit()
        report_id, run_id = item.id, run.id

    result = await server.call_tool("explain_report_schedule", {"reportScheduleId": report_id}, ctx=ctx)

    assert result["title"] == "Weekly report"
    assert result["bookmarkItemId"] == "bookmark-1"
    assert result["channels"] == ["webhook"]
    assert result["lastRunAt"] is not None
```

Adapt the exact call convention (`server.call_tool(...)` vs directly invoking the registered async function) to whatever `test_mcp_tools_alert.py` actually does — that file is the ground truth for this harness, do not guess its shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_tools_report.py -v`
Expected: FAIL — tool `explain_report_schedule` not found / not registered.

- [ ] **Step 3: Add the tool**

In `core/app/mcp/tools.py`, add the import next to the other domain-repository imports:
```python
from app.pipelines import repository as pipelines_repo
from app.reports import repository as reports_repo
```

Add the tool immediately after the existing `explain_alert_rule` block (right before `get_sharing`), at the same top-level indentation (unconditional — no `is_etl_enabled()`/`is_export_enabled()` gate, mirroring `explain_alert_rule`):

```python
    @server.tool()
    async def explain_report_schedule(ctx: Context, reportScheduleId: str) -> dict:
        """Describe a ReportSchedule (target bookmark, cron, channels, last
        run) without triggering it — mirrors explain_alert_rule's shape.
        Registered unconditionally (no capability flag). SP-17b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, reportScheduleId)
            if config is None or config.config.kind != "report":
                raise ValueError("report schedule not found")
            facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=reportScheduleId)
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("report schedule not found")
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=reportScheduleId)
            if item is None:
                raise ValueError("report schedule not found")
            payload = config.config.report
            assert payload is not None
            latest = reports_repo.get_latest_run(
                session, tenant_id=user.tenant_id, report_item_id=reportScheduleId,
            )
            return {
                "title": item.title,
                "bookmarkItemId": payload.bookmarkItemId,
                "refreshPolicy": payload.refreshPolicy.model_dump(),
                "channels": [c.kind for c in payload.channels],
                "lastRunAt": latest.created_at.isoformat() if latest else None,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_report.py tests/test_mcp_tools_alert.py -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/mcp/tools.py core/tests/test_mcp_tools_report.py
git commit -m "feat(core): MCP explain_report_schedule tool (SP-17b)"
```

---

## Task 14: Shell — types, `ItemClient`, hooks

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: none new (these are thin wiring layers, exercised transitively by Tasks 15-19's component tests and E2E).

**Interfaces:**
- Produces: `ReportSchedulePayload`, `ReportRunStatus` types; `createReportScheduleItem`, `getReportScheduleConfig`, `saveReportScheduleConfig`, `getReportRuns` on `ItemClient`; `useCreateReportSchedule`, `useReportScheduleConfig`, `useSaveReportSchedule` hooks — consumed by Tasks 15-17.

- [ ] **Step 1: Add `"report"` to `ResourceType` and the two new types**

In `shell/src/api/types.ts`, change:
```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert";
```
to:
```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert" | "report";
```

Add, right after `AlertRuleSummary`/`AlertEvaluation` (they're the closest sibling shapes):
```ts
export interface ReportSchedulePayload {
  bookmarkItemId: string;
  refreshPolicy: PipelineRefreshPolicy; // reused verbatim, same shape as pipeline/alert scheduling
  channels: AlertChannel[]; // reused verbatim from AlertRule (SP-16b)
}

export interface ReportRunStatus {
  id: string;
  status: "pending" | "running" | "done" | "error" | "unknown";
  resultUrl: string | null;
  error: string | null;
  notifiedAt: string | null;
  createdAt: string;
}
```

- [ ] **Step 2: Add `ItemClient` methods**

In the `ItemClient` interface block (`shell/src/api/types.ts`), add near the alert methods:
```ts
  createReportScheduleItem(input: { title: string; owner: string; report: ReportSchedulePayload }): Promise<Item>;
  getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload>;
  saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void>;
  getReportRuns(pk: string): Promise<ReportRunStatus[]>;
```

In `shell/src/api/itemClient.ts`, add right after the existing `getAlertEvaluations` method:
```ts
    async createReportScheduleItem(input: { title: string; owner: string; report: ReportSchedulePayload }): Promise<Item> {
      const config = { version: 1, kind: "report", report: input.report };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createReportScheduleItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "report", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload> {
      const data = await request<{ config?: { report?: ReportSchedulePayload } }>(
        "GET", `/configs/by-item/${pk}`,
      );
      if (!data.config?.report) throw new Error("getReportScheduleConfig: config has no report payload");
      return data.config.report;
    },

    async saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "report", report: payload });
    },

    async getReportRuns(pk: string): Promise<ReportRunStatus[]> {
      return request<ReportRunStatus[]>("GET", `/reports/${pk}/runs`);
    },
```

- [ ] **Step 3: Add hooks**

In `shell/src/api/hooks.ts`, add right after `useCreateAlertRule`:
```ts
export function useCreateReportSchedule() {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; report: ReportSchedulePayload }) =>
      client.createReportScheduleItem(input),
  });
}

export function useReportScheduleConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["report-schedule", pk],
    queryFn: () => client.getReportScheduleConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveReportSchedule(pk: string) {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (payload: ReportSchedulePayload) => client.saveReportScheduleConfig(pk, payload),
  });
}
```

Add `ReportSchedulePayload` to this file's existing type import from `./types` (do not add a second import statement — extend the existing one, matching how `AlertRulePayload`/`PipelineRefreshPolicy` are already imported there).

- [ ] **Step 4: Typecheck**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` passes — no unresolved references, no unused-import errors.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts
git commit -m "feat(shell): ReportSchedule types, ItemClient methods, hooks (SP-17b)"
```

---

## Task 15: `ReportScheduleEditor.tsx`

**Files:**
- Create: `shell/src/builder/report/ReportScheduleEditor.tsx`
- Test: exercised via Task 17's `ReportEditPage` and Task 19's E2E spec (this component has no data fetching of its own — it's a controlled form, same as `PipelineScheduleEditor`).

**Interfaces:**
- Consumes: `PipelineScheduleEditor` (existing, `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`), `PipelineRefreshPolicy`/`AlertChannel`/`ReportSchedulePayload` types.
- Produces: `ReportScheduleEditor({ value, onChange, bookmarkLabel }: { value: ReportSchedulePayload; onChange: (next: ReportSchedulePayload) => void; bookmarkLabel: string })` — a controlled form, no internal save logic (the parent `ReportEditPage`, Task 17, owns saving — mirrors `PipelineScheduleEditor`'s controlled-component shape, NOT `AlertRuleEditor`'s self-contained-create shape, since a `ReportSchedule` needs a full edit lifecycle with a run panel, unlike an alert rule which is create-only from `DatasetEditPage`). `bookmarkLabel` is display-only (Task 17 passes `draft.bookmarkItemId` — the raw id, since no bookmark-title lookup is in scope for this plan).

- [ ] **Step 1: Write the component**

```tsx
// shell/src/builder/report/ReportScheduleEditor.tsx
// SPDX-License-Identifier: Apache-2.0
import type { AlertChannel, ReportSchedulePayload } from "../../api/types";
import { PipelineScheduleEditor } from "../pipeline/PipelineScheduleEditor";

// Controlled component (mirrors PipelineScheduleEditor's value/onChange
// shape, not AlertRuleEditor's self-contained create-and-reset shape):
// ReportEditPage (SP-17b) needs both a create AND an edit lifecycle plus a
// run-history panel alongside it, so the parent owns persistence — same
// reason PipelineBuilderPage owns PipelinePayload state instead of
// PipelineScheduleEditor owning it.
export function ReportScheduleEditor({
  value, onChange, bookmarkLabel,
}: {
  value: ReportSchedulePayload;
  onChange: (next: ReportSchedulePayload) => void;
  bookmarkLabel: string;
}) {
  function setChannel(channel: AlertChannel) {
    onChange({ ...value, channels: [channel] });
  }
  const channel: AlertChannel | undefined = value.channels[0];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Vue ciblée : <span className="font-medium">{bookmarkLabel}</span>
      </p>

      <label className="flex flex-col gap-1 text-sm">
        Canal
        <select
          className="rounded border border-slate-300 px-2 py-1"
          value={channel?.kind ?? "webhook"}
          onChange={(e) => {
            if (e.target.value === "webhook") setChannel({ kind: "webhook", url: "" });
            else setChannel({ kind: "email", to: "", smtpSecretName: "" });
          }}
        >
          <option value="webhook">Webhook</option>
          <option value="email">E-mail</option>
        </select>
      </label>

      {channel?.kind === "webhook" && (
        <label className="flex flex-col gap-1 text-sm">
          URL du webhook
          <input
            className="rounded border border-slate-300 px-2 py-1"
            value={channel.url}
            onChange={(e) => setChannel({ kind: "webhook", url: e.target.value })}
          />
        </label>
      )}

      {channel?.kind === "email" && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            Destinataire
            <input
              className="rounded border border-slate-300 px-2 py-1"
              value={channel.to}
              onChange={(e) => setChannel({ kind: "email", to: e.target.value, smtpSecretName: channel.smtpSecretName })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Secret SMTP
            <input
              className="rounded border border-slate-300 px-2 py-1"
              value={channel.smtpSecretName}
              onChange={(e) => setChannel({ kind: "email", to: channel.to, smtpSecretName: e.target.value })}
            />
          </label>
        </>
      )}

      <PipelineScheduleEditor
        value={value.refreshPolicy}
        onChange={(policy) => onChange({ ...value, refreshPolicy: policy ?? { enabled: false, cron: "0 8 * * MON" } })}
      />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/builder/report/ReportScheduleEditor.tsx
git commit -m "feat(shell): ReportScheduleEditor — controlled form for channel + cron (SP-17b)"
```

---

## Task 16: `ReportRunPanel.tsx`

**Files:**
- Create: `shell/src/builder/report/ReportRunPanel.tsx`

**Interfaces:**
- Consumes: `useItemClient()` (existing), `client.getReportRuns(pk)` (Task 14).
- Produces: `ReportRunPanel({ reportId }: { reportId: string })` — read-only poll panel, no "Exécuter" button (reports are sweep-triggered only, never manually run).

- [ ] **Step 1: Write the component**

```tsx
// shell/src/builder/report/ReportRunPanel.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ReportRunStatus } from "../../api/types";

const STATUS_LABEL: Record<ReportRunStatus["status"], string> = {
  pending: "En attente", running: "En cours", done: "Terminé",
  error: "Échec", unknown: "Inconnu",
};

// Read-only history — mirrors PipelineRunPanel's poll loop (same 1500ms
// pattern as ImportFileButton) minus the "Exécuter" button: a ReportSchedule
// is only ever triggered by sweep_report_schedules_task's cron, never
// manually, so there is nothing for a button here to defer.
export function ReportRunPanel({ reportId }: { reportId: string }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<ReportRunStatus[]>([]);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    async function poll() {
      if (stopped.current) return;
      try {
        const next = await client.getReportRuns(reportId);
        if (!stopped.current) setRuns(next);
      } catch {
        /* transient poll failure — retry on next tick */
      }
      if (!stopped.current) setTimeout(poll, 1500);
    }
    poll();
    return () => {
      stopped.current = true;
    };
  }, [client, reportId]);

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Historique des exécutions</h3>
      {runs.length === 0 && <p className="text-sm text-slate-500">Aucune exécution pour l'instant.</p>}
      <ul className="flex flex-col gap-1">
        {runs.map((run) => (
          <li key={run.id} className="flex items-center gap-2 text-sm">
            <span>{STATUS_LABEL[run.status]}</span>
            <span className="text-slate-400">{new Date(run.createdAt).toLocaleString()}</span>
            {run.resultUrl && (
              <a href={run.resultUrl} className="text-blue-600 underline" target="_blank" rel="noreferrer">
                Télécharger
              </a>
            )}
            {run.error && <span className="text-red-600">{run.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/builder/report/ReportRunPanel.tsx
git commit -m "feat(shell): ReportRunPanel — read-only run history poll (SP-17b)"
```

---

## Task 17: `ReportEditPage.tsx` + routing

**Files:**
- Create: `shell/src/pages/ReportEditPage.tsx`
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `ReportScheduleEditor` (Task 15), `ReportRunPanel` (Task 16), `useCreateReportSchedule`/`useReportScheduleConfig`/`useSaveReportSchedule` (Task 14), `useAuth().username` (existing).
- Produces: `ReportEditPage({ pk, initialBookmarkItemId }: { pk: string | null; initialBookmarkItemId?: string })`; routes `/reports`, `/reports/new`, `/reports/:pk/edit`.

- [ ] **Step 1: Write `ReportEditPage.tsx`**

```tsx
// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateReportSchedule, useReportScheduleConfig, useSaveReportSchedule } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import type { ReportSchedulePayload } from "../api/types";
import { Button } from "../ui/button";
import { ReportScheduleEditor } from "../builder/report/ReportScheduleEditor";
import { ReportRunPanel } from "../builder/report/ReportRunPanel";

function defaultPayload(bookmarkItemId: string): ReportSchedulePayload {
  return {
    bookmarkItemId,
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
}

// pk === null : brouillon local (/reports/new) — mirrors PipelineBuilderPage's
// pk-nullable create/edit split exactly (SP-15b §2.2's rationale applies
// verbatim here: nothing persisted before the first "Enregistrer").
export function ReportEditPage({ pk, initialBookmarkItemId }: { pk: string | null; initialBookmarkItemId?: string }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const configQuery = useReportScheduleConfig(pk ?? "", { enabled: pk !== null });
  const createReport = useCreateReportSchedule();
  const saveReport = useSaveReportSchedule(pk ?? "");

  const [draft, setDraft] = useState<ReportSchedulePayload>(
    defaultPayload(initialBookmarkItemId ?? ""),
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createReport.mutateAsync({ title: "Rapport planifié", owner: username ?? "", report: draft });
        navigate(`/reports/${item.pk}/edit`, { replace: true });
        return;
      }
      await saveReport.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-medium">{pk === null ? "Programmer un rapport" : "Modifier le rapport planifié"}</h1>
      <ReportScheduleEditor value={draft} onChange={setDraft} bookmarkLabel={draft.bookmarkItemId} />
      <Button onClick={onSave} disabled={createReport.isPending || saveReport.isPending}>
        Enregistrer
      </Button>
      {saveError && (
        <p role="alert" className="text-sm text-red-600">
          {saveError}
        </p>
      )}
      {pk !== null && <ReportRunPanel reportId={pk} />}
    </div>
  );
}
```

- [ ] **Step 2: Wire routes**

In `shell/src/shell/routes.tsx`, add the import:
```ts
import { ReportEditPage } from "../pages/ReportEditPage";
```

Add two route-wrapper functions, right after `PipelineEditRoute`:
```tsx
function ReportNewRoute() {
  const location = useLocation();
  const bookmarkItemId = (location.state as { bookmarkItemId?: string } | null)?.bookmarkItemId;
  return <ReportEditPage pk={null} initialBookmarkItemId={bookmarkItemId} />;
}

function ReportEditRoute() {
  const { pk } = useParams();
  return <ReportEditPage pk={pk!} />;
}

function ReportsRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <>
      {openError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'ouverture du rapport.
        </p>
      )}
      <CatalogPage onOpenItem={onOpenItem} fixedType="report" />
    </>
  );
}
```

Add the `"report"` branch to `useOpenItem`, right before the final catch-all `navigate(...)` line:
```tsx
    if (type === "pipeline") {
      navigate(`/pipelines/${pk}/edit`);
      return;
    }
    if (type === "report") {
      navigate(`/reports/${pk}/edit`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
```

Register the three routes inside `<Route element={<ProtectedLayout />}>`, right after `/pipelines/:pk/edit`:
```tsx
        <Route path="/pipelines/:pk/edit" element={<PipelineEditRoute />} />
        <Route path="/reports" element={<ReportsRoute />} />
        <Route path="/reports/new" element={<ReportNewRoute />} />
        <Route path="/reports/:pk/edit" element={<ReportEditRoute />} />
```

- [ ] **Step 3: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 4: Run existing shell unit tests**

Run: `cd shell && npm run test -- routes`
Expected: PASS, no regressions (if `routes.tsx` has no dedicated unit test file, this step is a no-op — confirm by checking `shell/src` for a `routes.test.tsx` before assuming).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/pages/ReportEditPage.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): ReportEditPage + /reports routes (SP-17b)"
```

---

## Task 18: "Programmer un rapport" entry point on bookmark rows

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx`

**Interfaces:**
- Consumes: `useNavigate` (react-router-dom), `item.resourceType`/`item.pk` (existing `Item` type).
- Produces: one new conditional menu entry, no new exported symbol.

- [ ] **Step 1: Add the menu entry**

In `shell/src/shell/ItemActions.tsx`, add the import:
```tsx
import { useNavigate } from "react-router-dom";
```

Add `const navigate = useNavigate();` at the top of the component body, alongside the existing hooks:
```tsx
export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [panel, setPanel] = useState<Panel>(null);
```

Add the conditional entry in the menu block, right after "Modifier" (before "Publier" — matches the design's "entonnoir contextuel" placement, first action after edit):
```tsx
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("edit")}>
            Modifier
          </button>
          {item.resourceType === "bookmark" && (
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => {
                setPanel(null);
                navigate("/reports/new", { state: { bookmarkItemId: item.pk } });
              }}
            >
              Programmer un rapport
            </button>
          )}
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Run shell unit tests**

Run: `cd shell && npm run test`
Expected: PASS, no regressions (in particular any existing `ItemActions`/`CatalogPage` tests).

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/ItemActions.tsx
git commit -m "feat(shell): 'Programmer un rapport' entry point on bookmark rows (SP-17b)"
```

---

## Task 19: E2E — `report-schedule.spec.ts`

**Files:**
- Create: `shell/e2e/report-schedule.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (existing, `shell/e2e/mocks.ts`) — this codebase's E2E convention mocks every core route via `page.route(...)` rather than triggering a real procrastinate sweep (confirmed by reading `alert-rule.spec.ts`/`bookmarks.spec.ts`); this spec follows the same convention rather than the design doc's more literal "déclencher le sweep" phrasing.

- [ ] **Step 1: Write the E2E spec**

```ts
// shell/e2e/report-schedule.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-17b — depuis "Mes vues", programmer un rapport PDF hebdomadaire sur un
// signet existant, avec un webhook comme canal ; l'historique des
// exécutions affiche un run "Terminé" avec un lien de téléchargement.
test("programmer un rapport sur un signet, voir son historique d'exécutions", async ({ page }) => {
  await mockCore(page);

  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          { pk: "bookmark-1", resourceType: "bookmark", title: "Récents 2026", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-bookmark", isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      },
    });
  });

  let createdReportConfig: unknown = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    if (body?.config?.kind === "report") {
      createdReportConfig = body;
      await route.fulfill({ status: 201, json: { id: "cfg-report", kind: "report", itemId: "report-1" } });
      return;
    }
    return route.fallback();
  });
  await page.route("**/configs/by-item/report-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-report", itemId: "report-1", kind: "report",
        config: (createdReportConfig as { config: unknown })?.config ?? {
          kind: "report",
          report: { bookmarkItemId: "bookmark-1", refreshPolicy: { enabled: true, cron: "0 8 * * MON" }, channels: [{ kind: "webhook", url: "https://example.test/hook" }] },
        },
      },
    });
  });
  await page.route("**/reports/report-1/runs", async (route) => {
    await route.fulfill({
      json: [{
        id: "run-1", status: "done", resultUrl: "https://s3.test/renders/run-1.pdf",
        error: null, notifiedAt: "2026-08-09T08:00:05Z", createdAt: "2026-08-09T08:00:00Z",
      }],
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Programmer un rapport" }).click();
  await expect(page).toHaveURL(/\/reports\/new$/);

  await page.getByLabel("URL du webhook").fill("https://example.test/hook");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page).toHaveURL(/\/reports\/report-1\/edit$/);

  expect(createdReportConfig).not.toBeNull();
  expect(createdReportConfig).toMatchObject({
    config: {
      kind: "report",
      report: {
        bookmarkItemId: "bookmark-1",
        channels: [{ kind: "webhook", url: "https://example.test/hook" }],
      },
    },
  });

  await expect(page.getByText("Terminé")).toBeVisible();
  await expect(page.getByRole("link", { name: "Télécharger" })).toHaveAttribute("href", "https://s3.test/renders/run-1.pdf");
});
```

Before finalizing, read `shell/e2e/mocks.ts` to confirm `mockCore`'s exact default fixtures (auth identity, base `**/items*` handler, etc.) match what this spec assumes — adjust route order/specificity if `mockCore` already registers a `**/items*` handler that would intercept before this spec's own override (Playwright matches routes in reverse registration order, most-recently-registered first, same as every other spec in this directory already relies on).

- [ ] **Step 2: Run the E2E spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test report-schedule.spec.ts`
Expected: PASS.

- [ ] **Step 3: Run the full E2E suite to confirm no regression**

Run: `cd shell && npm run e2e`
Expected: PASS (previous 18 specs + this new one = 19), no regressions.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/e2e/report-schedule.spec.ts
git commit -m "test(shell): E2E — programmer un rapport sur un signet (SP-17b)"
```

---

## Final Verification

- [ ] **Full core suite**: `cd core && uv run pytest -q` — expect all green (SQLite-backed tests only; `postgis`-marked skip without `CORE_TEST_DATABASE_URL`).
- [ ] **Import-linter**: `cd core && uv run lint-imports` — no violations.
- [ ] **Core typecheck/lint** (if configured): `cd core && uv run ruff check .` — no new issues in touched files.
- [ ] **Shell build**: `cd shell && npm run build` — `tsc --noEmit` + `vite build` both succeed.
- [ ] **Shell unit tests**: `cd shell && npm run test` — all green, no regressions against the pre-existing 61 files / 398 tests.
- [ ] **Shell E2E**: `cd shell && npm run e2e` — all 19 specs green.
- [ ] **Real-Postgres migration check** (Tasks 3 & 6, if not already done inline): `cd core && DATABASE_URL=<real postgres> uv run alembic upgrade head` reaches `0023 (head)` cleanly.
- [ ] Re-read `docs/superpowers/specs/2026-08-09-sp17b-report-schedule-design.md`'s "Critères d'acceptation" section and confirm each one is now demonstrably true against the code (not just "a task claims to implement it").
