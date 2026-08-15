# SP-18a — Export d'apps : mécanisme commun + mode Statique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author export a published app/dashboard from the builder as a
self-contained static bundle (HTML/JS/CSS + frozen JSON data) that runs on
any static host, with zero GeoStudio backend — the first of SP-18's three
export modes, plus the guard/job/route mechanism the other two modes
(Connecté, Autoporté — separate later plans, SP-18b/c) will reuse.

**Architecture:** A new core module `app.appexport` exposes
`POST /app-exports` (guard the config's DataSources for public sharing →
defer a procrastinate job) and `GET /app-exports/jobs/{id}` (poll), mirroring
`app.export`'s (SP-17a) job/route shape exactly. The job rewrites every
`"features"`-type `DataSource` into a self-contained `"static"` one (fetching
real rows via the same in-process calls `app.mcp.tools` already uses,
`introspect_table`/`select_features`), producing a config that needs no
backend at all — this reuses `ItemClient`'s pre-existing `"static"`
DataSource branch (`return query.records`) verbatim, so the shell-side
`StaticItemClient` needs almost no new query logic. The job then zips that
frozen config together with a **prebuilt, generic, app-agnostic** static
runtime bundle (built once via a new Vite entry, not rebuilt per export) and
uploads it to S3. No Node/Vite ever runs inside the job itself.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic/procrastinate (core, existing
patterns), Vite/React/TypeScript (shell, existing patterns), boto3/MinIO (S3,
existing patterns).

## Global Constraints

- Capability-gated, default off: `CORE_APPEXPORT_ENABLED` (env var), read via
  `is_appexport_enabled()` — same convention as `is_export_enabled()`
  (`core/app/auth/dependency.py`): read fresh on every call, no cache, so
  tests can monkeypatch without recreating the app.
- SP-18a's Statique mode supports only `DataSource` types `"features"` and
  `"static"`. Any `"statistics"`-type `DataSource` in the config makes the
  export guard refuse, with an explicit per-source message — aggregate
  freezing is deferred to a fast-follow (documented, not built here).
- SP-18a's Statique mode supports only the 22 builtin widget types already
  registered by `registerBuiltinWidgets()` (see Task 4 for the exact list).
  Any other widget type (third-party SP-8 extension) makes the guard refuse.
  Nested widgets inside container widgets (tabs/modal/drawer) are **not**
  scanned by the guard in v1 (their contents live in untyped `props: dict`
  server-side, invisible to a typed walk) — documented gap, not a data-leak
  risk (the DataSource guard is unaffected, since `dataSources` is a
  top-level, global list, not nested inside widget props).
- The export guard checks **every** entry in `config.dataSources`, not only
  ones actually wired to a visible widget — simpler, and never less safe
  than a usage-based check (spec §3 says literally "chaque DataSource").
- A `DataSource`'s underlying collection must have `Collection.is_public =
  true` (not merely group-shared/`can()`-readable) — the artifact runs with
  zero authenticated session, so anything short of fully public would leak
  non-public data to whoever opens the exported bundle.
- **Discovered during research, load-bearing for this plan's design (not a
  bug to fix here):** `app.configs.schemas.DataSource` has no `datasetId`
  field, and pydantic v2's default `extra="ignore"` silently drops any
  `datasetId` key sent by the client on every `BuilderConfig.model_validate`
  round-trip (verified empirically, `core/app/configs/repository.py`
  persists `config.model_dump(by_alias=True)`, never the raw client dict).
  A **persisted** app config's `DataSource.layer` is therefore always the
  literal collection id already — the guard/freeze code in this plan
  operates on `source.layer` directly and never needs dataset-item
  resolution (`getDatasetConfig`/`resolveDataset`, a purely client-side,
  same-session cache). This is simpler than — and consistent with — how the
  server already treats `DataSource.layer` everywhere else.
- New core module `app.appexport` sits in the import-linter layer contract
  (`core/pyproject.toml`) directly below `app.export` (same rung-depth
  reasoning as `app.export`: needs `app.configs`, `app.collections`,
  `app.items`, `app.sharing`, `app.features.repository`,
  `app.collections.introspection_pg`, all already below `app.export`).
- Server-side query/aggregate calls made **in-process**, mirroring
  `app/mcp/tools.py`'s established pattern (`introspect_table`,
  `rls_scope`, `select_features`) — never an HTTP self-call.
- No dedicated Docker image for this job (unlike SP-17a's Chromium-heavy
  `export-worker`): it only copies files and zips, so it runs on the shared
  `worker` service, queue `appexport` added to its existing queue list.
- Every code step in this plan follows TDD (failing test → minimal
  implementation → passing test → commit), per this repo's CLAUDE.md.

---

## File structure

**Core (`core/`)**
- Create `core/app/appexport/__init__.py`, `models.py`, `repository.py`,
  `guard.py`, `freeze.py`, `bundler.py`, `jobs.py`, `routes.py`
- Create `core/alembic/versions/0027_app_export_jobs.py`
- Modify `core/app/auth/dependency.py` — add `is_appexport_enabled()`
- Modify `core/app/main.py` — mount router, S3 bucket override
- Modify `core/app/jobs.py` — add `"app.appexport.jobs"` to `import_paths`
- Modify `core/app/instance/routes.py` — add `appExportEnabled`
- Modify `core/pyproject.toml` — import-linter layer + ignore_imports entry
- Create `core/tests/test_appexport_repository.py`,
  `test_appexport_guard.py`, `test_appexport_freeze.py`,
  `test_appexport_jobs.py`, `test_appexport_routes.py`

**Shell (`shell/`)**
- Create `shell/index.export.html`
- Create `shell/src/staticExport/entry.tsx`, `StaticItemClient.ts`
- Create `shell/vite.export.config.ts`
- Modify `shell/package.json` — `build:export-runtime` script
- Modify `shell/src/api/types.ts` — new types, `InstanceInfo.appExportEnabled`
- Modify `shell/src/api/itemClient.ts` — `createAppExport`/`getAppExportJob`
- Create `shell/src/builder/appexport/AppExportPanel.tsx`,
  `collectWidgetTypes.ts`
- Modify `shell/src/pages/AppBuilderPage.tsx` — mount the panel
- Create `shell/src/staticExport/StaticItemClient.test.ts`,
  `shell/src/builder/appexport/AppExportPanel.test.tsx`,
  `shell/src/builder/appexport/collectWidgetTypes.test.ts`
- Create `shell/e2e/static-export.spec.ts`

**Infra**
- Create `deploy/appexport-runtime-builder/Dockerfile`
- Modify `docker-compose.yml` — new one-shot service + volume, `worker`
  queue list + env vars + volume mount, `core` env var

---

### Task 1: `AppExportJob` model + migration

**Files:**
- Create: `core/app/appexport/__init__.py` (empty)
- Create: `core/app/appexport/models.py`
- Create: `core/alembic/versions/0027_app_export_jobs.py`
- Test: `core/tests/test_appexport_repository.py` (created fully in Task 2;
  this task only needs the table to exist for that test to run against
  SQLite via `init_db`)

**Interfaces:**
- Produces: `AppExportJob` ORM class (table `app_export_jobs`), columns
  `id: str`, `tenant_id: str`, `item_id: str`, `user_id: str`, `mode: str`,
  `status: str` (default `"pending"`), `error: str | None`,
  `result_key: str | None`, `started_at: datetime | None`,
  `finished_at: datetime | None`, `created_at: datetime`.

- [ ] **Step 1: Write `models.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""app.appexport (SP-18a) — export d'une app/dashboard en bundle
autoporté. Mode "static" seul supporté pour l'instant ; "connected" et
"standalone" (SP-18b/c) réutiliseront la même table (colonne `mode`
existe déjà, pas de migration à refaire)."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AppExportJob(Base):
    __tablename__ = "app_export_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 2: Write the migration**

```python
# SPDX-License-Identifier: Apache-2.0
"""app.appexport — app_export_jobs

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_export_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("result_key", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_app_export_jobs_tenant_id", "app_export_jobs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_app_export_jobs_tenant_id", table_name="app_export_jobs")
    op.drop_table("app_export_jobs")
```

- [ ] **Step 3: Register the model for SQLite test metadata + import-linter ignore**

In `core/pyproject.toml`, under `[tool.importlinter.contracts]` →
`ignore_imports`, add (keeps `app.db`'s metadata-registration import from
tripping the layer contract, same reason as the 16 existing entries):

```toml
    "app.db -> app.appexport.models",
```

- [ ] **Step 4: Run the core test suite to confirm nothing broke**

Run: `cd core && uv run pytest tests/test_import_linter.py -q` (or
whatever the layer-contract test file is named — confirm via
`grep -rl importlinter core/tests`)
Expected: PASS (new module has no code yet beyond an empty `__init__.py` +
`models.py`, so nothing to violate).

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/__init__.py core/app/appexport/models.py \
  core/alembic/versions/0027_app_export_jobs.py core/pyproject.toml
git commit -m "feat(core): app_export_jobs table (SP-18a)"
```

---

### Task 2: `app.appexport` repository

**Files:**
- Create: `core/app/appexport/repository.py`
- Test: `core/tests/test_appexport_repository.py`

**Interfaces:**
- Consumes: `AppExportJob` (Task 1).
- Produces: `create_job(session, *, tenant_id, item_id, user_id, mode) ->
  AppExportJob`, `get_job(session, *, tenant_id, job_id) -> AppExportJob |
  None`, `mark_running(session, *, job_id) -> None`, `mark_done(session, *,
  job_id, result_key) -> None`, `mark_error(session, *, job_id, error) ->
  None`, `reclaim_stuck_jobs(session, *, older_than_minutes=60) ->
  list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.appexport import repository as appexport_repo
from app.appexport.models import AppExportJob
from app.db import init_db, make_engine, make_session_factory


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_create_and_get_job():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        fetched = appexport_repo.get_job(s, tenant_id="t1", job_id=job.id)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.mode == "static"


def test_get_job_wrong_tenant_returns_none():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        assert appexport_repo.get_job(s, tenant_id="other", job_id=job.id) is None


def test_mark_running_then_done():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        appexport_repo.mark_running(s, job_id=job.id)
        s.commit()
        fetched = appexport_repo.get_job(s, tenant_id="t1", job_id=job.id)
        assert fetched.status == "running"
        assert fetched.started_at is not None

        appexport_repo.mark_done(s, job_id=job.id, result_key="appexports/x.zip")
        s.commit()
        fetched = appexport_repo.get_job(s, tenant_id="t1", job_id=job.id)
        assert fetched.status == "done"
        assert fetched.result_key == "appexports/x.zip"
        assert fetched.finished_at is not None


def test_mark_error():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        appexport_repo.mark_error(s, job_id=job.id, error="boom")
        s.commit()
        fetched = appexport_repo.get_job(s, tenant_id="t1", job_id=job.id)
        assert fetched.status == "error"
        assert fetched.error == "boom"


def test_reclaim_stuck_jobs_anchors_on_started_at():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        appexport_repo.mark_running(s, job_id=job.id)
        # Backdate started_at past the reclaim threshold directly (same
        # pattern as core/tests/test_export_repository.py).
        row = s.get(AppExportJob, job.id)
        row.started_at = datetime.now(timezone.utc) - timedelta(minutes=90)
        s.commit()

        reclaimed = appexport_repo.reclaim_stuck_jobs(s, older_than_minutes=60)
        s.commit()
        assert reclaimed == [job.id]
        fetched = appexport_repo.get_job(s, tenant_id="t1", job_id=job.id)
        assert fetched.status == "error"


def test_reclaim_stuck_jobs_ignores_recent_running():
    Session = _session()
    with Session() as s:
        job = appexport_repo.create_job(
            s, tenant_id="t1", item_id="item1", user_id="u1", mode="static",
        )
        s.commit()
        appexport_repo.mark_running(s, job_id=job.id)
        s.commit()

        reclaimed = appexport_repo.reclaim_stuck_jobs(s, older_than_minutes=60)
        assert reclaimed == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_repository.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.appexport.repository'`)

- [ ] **Step 3: Write `repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Même discipline de reclaim-par-âge que app.export.repository (anchored on
# started_at, jamais created_at — un job resté "pending" en file avant de
# démarrer ne doit pas être réclamé dès qu'il passe "running").
_RUNNING_RECLAIM_MINUTES = 60


def create_job(
    session: Session, *, tenant_id: str, item_id: str, user_id: str, mode: str,
) -> AppExportJob:
    job = AppExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        mode=mode, status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> AppExportJob | None:
    return session.execute(
        select(AppExportJob).where(AppExportJob.id == job_id, AppExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = _now()
    session.flush()


def mark_done(session: Session, *, job_id: str, result_key: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.result_key = result_key
    job.finished_at = _now()
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    job = session.get(AppExportJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error = error
    job.finished_at = _now()
    session.flush()


def reclaim_stuck_jobs(session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES) -> list[str]:
    threshold = _now() - timedelta(minutes=older_than_minutes)
    rows = session.execute(
        select(AppExportJob).where(AppExportJob.status == "running")
    ).scalars().all()
    reclaimed: list[str] = []
    for job in rows:
        started_at = job.started_at
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at >= threshold:
            continue
        job.status = "error"
        job.error = "app export timed out (worker crashed or hung)"
        job.finished_at = _now()
        reclaimed.append(job.id)
    if reclaimed:
        session.flush()
    return reclaimed
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_repository.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/repository.py core/tests/test_appexport_repository.py
git commit -m "feat(core): app_export_jobs repository (SP-18a)"
```

---

### Task 3: capability flag + import-linter layer entry

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_appexport_flag.py`

**Interfaces:**
- Produces: `is_appexport_enabled() -> bool` reading `CORE_APPEXPORT_ENABLED`
  (default `"false"`).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_appexport_enabled


def test_appexport_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CORE_APPEXPORT_ENABLED", raising=False)
    assert is_appexport_enabled() is False


def test_appexport_enabled_via_env(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    assert is_appexport_enabled() is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_flag.py -v`
Expected: FAIL (`ImportError: cannot import name 'is_appexport_enabled'`)

- [ ] **Step 3: Add the function**

In `core/app/auth/dependency.py`, after `is_export_enabled()`:

```python
def is_appexport_enabled() -> bool:
    """CORE_APPEXPORT_ENABLED (SP-18a) — capacité instance-wide optionnelle,
    même convention que is_export_enabled : lue à chaque appel, sans cache.
    Défaut false : construire un bundle statique d'app exige le runtime
    export prébâti (deploy/appexport-runtime-builder), jamais requis pour le
    reste de la plateforme."""
    return os.environ.get("CORE_APPEXPORT_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Add the import-linter layer entry**

In `core/pyproject.toml`, under `[[tool.importlinter.contracts]] layers =
[...]`, insert `"app.appexport",` directly below `"app.export",`:

```toml
    "app.export",
    "app.appexport",
    "app.tileset3d",
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_flag.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add core/app/auth/dependency.py core/pyproject.toml core/tests/test_appexport_flag.py
git commit -m "feat(core): CORE_APPEXPORT_ENABLED capability flag (SP-18a)"
```

---

### Task 4: export guard (sharing + widget-type)

**Files:**
- Create: `core/app/appexport/guard.py`
- Test: `core/tests/test_appexport_guard.py`

**Interfaces:**
- Consumes: `app.configs.schemas.BuilderConfig`, `app.collections.repository`
  (`get_collection`, `get_access_facts`).
- Produces: `ExportGuardResult` (dataclass, `allowed: bool`, `reasons:
  list[str]`), `check_export_guard(session, *, tenant_id: str, config:
  BuilderConfig) -> ExportGuardResult`.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.guard import check_export_guard
from app.collections.repository import create_collection, set_collection_sharing
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _app_config(*, data_sources, widget_types=("text",)) -> BuilderConfig:
    items = [
        LayoutItem(id=f"w{i}", widget=t, x=0, y=i, w=4, h=2)
        for i, t in enumerate(widget_types)
    ]
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        pages=[Page(id="p1", name="Page 1", layout=Layout(type="grid", items=items))],
    )


def test_no_data_sources_and_only_builtin_widgets_is_allowed():
    Session = _session()
    with Session() as s:
        result = check_export_guard(s, tenant_id="t1", config=_app_config(data_sources=[]))
    assert result.allowed is True
    assert result.reasons == []


def test_static_source_needs_no_check():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="static", service="core", layer="", query={"records": []}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config)
    assert result.allowed is True


def test_features_source_on_non_public_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        col = create_collection(
            s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
            title="X", geometry_type="point", srid=4326,
        )
        s.commit()
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant.id, config=config)
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_public_collection_is_allowed():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        col = create_collection(
            s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
            title="X", geometry_type="point", srid=4326,
        )
        set_collection_sharing(s, col=col, public=True)
        s.commit()
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant.id, config=config)
    assert result.allowed is True


def test_features_source_on_missing_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer="ghost", query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant.id, config=config)
    assert result.allowed is False
    assert any("introuvable" in r for r in result.reasons)


def test_statistics_source_is_blocked_v1():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer="x", query={}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config)
    assert result.allowed is False
    assert any("agrégat" in r for r in result.reasons)


def test_unsupported_widget_type_is_blocked():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config)
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write `guard.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a) : refuse tout export dont une DataSource
référence une collection non publique, ou qui contient un widget non
supporté par le mode Statique. Voir le plan §Global Constraints pour la
justification de is_public (pas can()) et du scan par-DataSource (pas par
widget câblé)."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig, LayoutItem

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
_SUPPORTED_WIDGET_TYPES = frozenset({
    "text", "image", "button", "table", "list", "map", "indicator", "chart",
    "pivot", "nav", "form", "hero", "richSection", "gallery", "datasetCard",
    "dateRangeFilter", "selectFilter", "sliderFilter", "tabs", "modal",
    "drawer", "filter",
})


@dataclass
class ExportGuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _collect_widget_types(config: BuilderConfig) -> set[str]:
    types: set[str] = set()
    for page in config.pages:
        for item in page.layout.items:
            types.add(item.widget)
    return types


def check_export_guard(session: Session, *, tenant_id: str, config: BuilderConfig) -> ExportGuardResult:
    reasons: list[str] = []

    for source in config.dataSources:
        if source.type == "static":
            continue
        if source.type == "statistics":
            reasons.append(
                f"source '{source.id}' : l'export statique ne supporte pas encore "
                "les sources de type agrégat (statistics)"
            )
            continue
        if source.type != "features":
            reasons.append(f"source '{source.id}' : type '{source.type}' non supporté")
            continue
        collection_id = source.layer
        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
        if col is None:
            reasons.append(f"source '{source.id}' : collection '{collection_id}' introuvable")
            continue
        facts = collections_repo.get_access_facts(col)
        if not facts.is_public:
            reasons.append(
                f"source '{source.id}' : collection '{collection_id}' n'est pas partagée publiquement"
            )

    unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
    for widget_type in sorted(unsupported):
        reasons.append(
            f"widget '{widget_type}' non supporté par l'export statique "
            "(extension tierce, non prise en charge)"
        )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: PASS (7 tests). If `create_collection`/`set_collection_sharing`
signatures differ from what's used above, adjust the test to match the real
signatures in `core/app/collections/repository.py` (read that file first —
Task 4's author must confirm exact kwargs before writing the test, since
this plan's signature guess is based on the repository function list seen
during planning, not a byte-for-byte read of every parameter).

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/guard.py core/tests/test_appexport_guard.py
git commit -m "feat(core): export guard — public sharing + widget allowlist (SP-18a)"
```

---

### Task 5: data freezing (`features` → `static`)

**Files:**
- Create: `core/app/appexport/freeze.py`
- Test: `core/tests/test_appexport_freeze.py`

**Interfaces:**
- Consumes: `BuilderConfig` (already guard-approved — caller's
  responsibility, `freeze_config` does not re-check sharing).
- Produces: `freeze_config(session, *, tenant_id: str, config: BuilderConfig,
  max_records_per_source: int = 50_000) -> BuilderConfig` — returns a new
  `BuilderConfig` where every `"features"`-type `DataSource` has been
  rewritten to `type="static"`, `query={"records": [...]}` (already-embedded
  `"static"` sources pass through unchanged).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.freeze import freeze_config
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory
from app.features.repository import insert_feature
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _app_config(data_sources) -> BuilderConfig:
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        pages=[Page(id="p1", name="Page 1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
        ))],
    )


def test_static_source_passes_through_unchanged():
    Session = _session()
    with Session() as s:
        config = _app_config([
            DataSource(id="s1", type="static", service="core", layer="", query={"records": [{"id": 1}]}),
        ])
        frozen = freeze_config(s, tenant_id="t1", config=config)
    assert frozen.dataSources[0].type == "static"
    assert frozen.dataSources[0].query["records"] == [{"id": 1}]


def test_features_source_is_frozen_into_static_records():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        col = create_collection(
            s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
            title="X", geometry_type="point", srid=4326,
        )
        s.commit()
        info = introspect_table(s, col.table_name)
        insert_feature(s, info, properties={"name": "Alpha"}, geometry=None)
        insert_feature(s, info, properties={"name": "Beta"}, geometry=None)
        s.commit()

        config = _app_config([
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        frozen = freeze_config(s, tenant_id=tenant.id, config=config)

    out = frozen.dataSources[0]
    assert out.type == "static"
    names = sorted(r["properties"]["name"] for r in out.query["records"])
    assert names == ["Alpha", "Beta"]


def test_config_shape_is_otherwise_unchanged():
    Session = _session()
    with Session() as s:
        config = _app_config([])
        frozen = freeze_config(s, tenant_id="t1", config=config)
    assert frozen.pages[0].id == "p1"
    assert frozen.kind == "app"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_freeze.py -v`
Expected: FAIL (`ModuleNotFoundError`). If `introspect_table`,
`insert_feature`, or `create_collection` signatures used in the test above
don't match reality, fix the test to match — read
`core/app/collections/introspection_pg.py` and
`core/app/features/repository.py` first for exact kwargs (this plan's guess
is based on the function list seen during planning, e.g.
`insert_feature(session, info, *, properties, geometry, ...)` per
`core/app/features/repository.py:171`).

- [ ] **Step 3: Write `freeze.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Gèle les DataSources "features" d'une config app/dashboard en
"static" (query.records embarqués) — même mécanisme in-process que
app/mcp/tools.py (introspect_table + select_features), jamais un
self-call HTTP. Le mode Statique n'a alors plus besoin d'aucun réseau au
runtime : ItemClient.queryDataSource traite déjà "static" en local
(shell/src/api/itemClient.ts, branche existante, inchangée)."""
from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.configs.schemas import BuilderConfig, DataSource
from app.features.repository import select_features


def freeze_config(
    session, *, tenant_id: str, config: BuilderConfig, max_records_per_source: int = 50_000,
) -> BuilderConfig:
    frozen_sources: list[DataSource] = []
    for source in config.dataSources:
        if source.type != "features":
            frozen_sources.append(source)
            continue
        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=source.layer)
        info = introspect_table(session, col.table_name)
        records: list[dict] = []
        offset = 0
        page_size = 1000
        while len(records) < max_records_per_source:
            page = select_features(session, info, limit=page_size, offset=offset, bbox=None, geom_intersects=None, filters=None)
            records.extend(page.features)
            if len(page.features) < page_size:
                break
            offset += page_size
        frozen_sources.append(DataSource(
            id=source.id, type="static", service=source.service, layer=source.layer,
            query={**source.query, "records": records[:max_records_per_source]},
        ))
    return config.model_copy(update={"dataSources": frozen_sources})
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_freeze.py -v`
Expected: PASS (3 tests). If `select_features`'s return type doesn't expose
`.features` as a list of `{"id", "properties", "geometry"}`-shaped dicts (it
returns GeoJSON Feature dicts per `app/features/routes.py`'s
`list_features`), adjust the assertion in Step 1 to match the real shape —
confirm by reading `core/app/features/repository.py`'s `_row_to_feature`
before finalizing.

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/freeze.py core/tests/test_appexport_freeze.py
git commit -m "feat(core): freeze features DataSources to static records (SP-18a)"
```

---

### Task 6: bundler (prebuilt runtime + frozen config → zip → S3)

**Files:**
- Create: `core/app/appexport/bundler.py`
- Test: `core/tests/test_appexport_bundler.py`

**Interfaces:**
- Consumes: `BuilderConfig` (frozen, Task 5's output), a filesystem path to
  the prebuilt export-runtime assets (env `APPEXPORT_RUNTIME_DIR`).
- Produces: `build_bundle_zip(config: BuilderConfig, *, runtime_dir: str) ->
  bytes` — a zip containing the runtime's `index.html`/`assets/*` plus one
  new file `geostudio-app-config.json` (the frozen config, `by_alias=True`)
  at the zip root, alongside a rewritten `index.html` whose inline bootstrap
  script tag references that JSON path (Task 9 defines the exact contract:
  `entry.tsx` fetches `./geostudio-app-config.json` via a same-origin
  relative `fetch`).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
import io
import zipfile

from app.appexport.bundler import build_bundle_zip
from app.configs.schemas import BuilderConfig, Layout, LayoutItem, Page


def _config() -> BuilderConfig:
    return BuilderConfig(
        kind="app", dataSources=[],
        pages=[Page(id="p1", name="Page 1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
        ))],
    )


def test_bundle_contains_runtime_assets_and_frozen_config(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html><body>runtime</body></html>")
    assets_dir = runtime_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "export-abc123.js").write_text("console.log('runtime js')")

    zip_bytes = build_bundle_zip(_config(), runtime_dir=str(runtime_dir))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "index.html" in names  # index.export.html renamed at zip root
        assert "assets/export-abc123.js" in names
        assert "geostudio-app-config.json" in names
        payload = zf.read("geostudio-app-config.json").decode("utf-8")
        assert '"kind"' in payload and '"app"' in payload


def test_bundle_raises_clearly_when_runtime_dir_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        build_bundle_zip(_config(), runtime_dir=str(tmp_path / "does-not-exist"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write `bundler.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Assemble le zip d'export Statique : runtime prébâti (Task 10, jamais
reconstruit par ce job) + config gelée (Task 5) sérialisée en JSON, lue au
runtime par shell/src/staticExport/entry.tsx via un fetch relatif — aucune
invocation Node/Vite ici."""
import io
import os
import zipfile

from app.configs.schemas import BuilderConfig


def build_bundle_zip(config: BuilderConfig, *, runtime_dir: str) -> bytes:
    entry_path = os.path.join(runtime_dir, "index.export.html")
    if not os.path.isfile(entry_path):
        raise FileNotFoundError(f"export runtime not found at {entry_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(entry_path, "rb") as f:
            zf.writestr("index.html", f.read())
        assets_dir = os.path.join(runtime_dir, "assets")
        if os.path.isdir(assets_dir):
            for name in os.listdir(assets_dir):
                with open(os.path.join(assets_dir, name), "rb") as f:
                    zf.writestr(f"assets/{name}", f.read())
        zf.writestr("geostudio-app-config.json", config.model_dump_json(by_alias=True))
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/bundler.py core/tests/test_appexport_bundler.py
git commit -m "feat(core): app export bundler — zip runtime + frozen config (SP-18a)"
```

---

### Task 7: procrastinate job

**Files:**
- Create: `core/app/appexport/jobs.py`
- Modify: `core/app/jobs.py` — add `"app.appexport.jobs"` to `import_paths`
- Test: `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes: `appexport_repo` (Task 2), `check_export_guard` (Task 4),
  `freeze_config` (Task 5), `build_bundle_zip` (Task 6),
  `configs_repo.get_config_by_item`, `is_appexport_enabled` (Task 3),
  `ensure_uploads_bucket`/`make_s3_client` (`app.ingestion.storage`,
  existing).
- Produces: `build_app_export_task(job_id: str, tenant_id: str) -> None`,
  registered `@app.task(queue="appexport")`.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport import repository as appexport_repo
from app.appexport.jobs import build_app_export_task
from app.collections.repository import create_collection, set_collection_sharing
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.repository import create_item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _setup(monkeypatch, tmp_path, *, with_private_source=False):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")
    monkeypatch.setenv("APPEXPORT_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "k")
    monkeypatch.setenv("S3_SECRET_KEY", "s")

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        data_sources = []
        if with_private_source:
            col = create_collection(
                s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_priv",
                title="Priv", geometry_type="point", srid=4326,
            )
            data_sources = [DataSource(id="s1", type="features", service="core", layer=col.id, query={})]
        item = create_item(s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="App")
        config = BuilderConfig(
            kind="app", dataSources=data_sources,
            pages=[Page(id="p1", name="P1", layout=Layout(
                type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
            ))],
        )
        configs_repo.create_config(s, config, item.id, tenant_id=tenant.id)
        job = appexport_repo.create_job(s, tenant_id=tenant.id, item_id=item.id, user_id=owner.id, mode="static")
        s.commit()
    return Session, tenant.id, job.id


def _fake_s3():
    class _Fake:
        def create_bucket(self, Bucket):  # noqa: N803
            pass

        def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
            pass

        def put_object(self, **kwargs):
            pass

    return _Fake()


def test_job_disabled_flag_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "disabled" in job.error


def test_job_succeeds_and_marks_done(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "done"
    assert job.result_key == f"appexports/{job_id}.zip"


def test_job_guard_rejection_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, with_private_source=True)
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "publique" in job.error
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write `jobs.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-18a) : guard → gèle les DataSources → assemble
le zip → upload S3. Tourne sur le worker partagé (queue `appexport`, pas de
Chromium/Node ici — voir plan §Global Constraints). Toute erreur marque le
job "error", jamais un job bloqué en "running" (même critère que
app.export.jobs/app.pipelines.jobs)."""
import logging
import os

from app.appexport import repository as appexport_repo
from app.appexport.bundler import build_bundle_zip
from app.appexport.freeze import freeze_config
from app.appexport.guard import check_export_guard
from app.auth.dependency import is_appexport_enabled
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


@app.task(queue="appexport")
def build_app_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_appexport_enabled():
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error="app export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        appexport_repo.mark_running(session, job_id=job_id)
        item_id = job.item_id

    try:
        with request_scoped_session(session_factory) as session:
            config_read = configs_repo.get_config_by_item(session, item_id)
            if config_read is None:
                raise ValueError(f"app export item '{item_id}' not found")
            guard_result = check_export_guard(session, tenant_id=tenant_id, config=config_read.config)
            if not guard_result.allowed:
                raise ValueError("; ".join(guard_result.reasons))
            frozen = freeze_config(session, tenant_id=tenant_id, config=config_read.config)

        runtime_dir = os.environ["APPEXPORT_RUNTIME_DIR"]
        zip_bytes = build_bundle_zip(frozen, runtime_dir=runtime_dir)

        result_key = f"appexports/{job_id}.zip"
        bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        s3_client = s3_client_from_env()
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(Bucket=bucket, Key=result_key, Body=zip_bytes, ContentType="application/zip")

        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("app export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
```

- [ ] **Step 4: Register the module on the shared worker**

In `core/app/jobs.py`, add `"app.appexport.jobs"` to the `import_paths`
list (alongside `"app.export.jobs"`):

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs", "app.appexport.jobs", "app.reports.jobs",
        "app.tileset3d.jobs", "app.terrain3d.jobs",
    ],
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add core/app/appexport/jobs.py core/app/jobs.py core/tests/test_appexport_jobs.py
git commit -m "feat(core): app export procrastinate job (SP-18a)"
```

---

### Task 8: REST routes + wiring (main.py, instance flag)

**Files:**
- Create: `core/app/appexport/routes.py`
- Modify: `core/app/main.py`
- Modify: `core/app/instance/routes.py`
- Test: `core/tests/test_appexport_routes.py`

**Interfaces:**
- Produces: `POST /app-exports` (body `{itemId, mode}` → `202 {jobId}`),
  `GET /app-exports/jobs/{job_id}` (→ `{id, status, resultUrl, error}`).
  `InstanceInfo` gains `appExportEnabled: bool`.

- [ ] **Step 1: Write the failing test**

Mirror `core/tests/test_export_routes.py` exactly (same `_FakeS3Client`,
`_fake_deferrer`, `env` fixture shape), swapping `format` for `mode` and the
`/export` path for `/app-exports`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.appexport import repository as appexport_repo
from app.appexport import routes as appexport_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.items.repository import create_item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


def _fake_deferrer():
    calls = []

    def deferrer(job_id, tenant_id):
        calls.append((job_id, tenant_id))

    return deferrer, calls


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        stranger = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        item = create_item(s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="App")
        configs_repo.create_config(
            s, BuilderConfig(kind="app", dataSources=[], pages=[]), item.id, tenant_id=tenant.id,
        )
        s.commit()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    fake_s3 = _FakeS3Client()

    def make_client():
        app = create_app()
        app.dependency_overrides[db.get_session] = override_session
        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
        deferrer, calls = _fake_deferrer()
        app.dependency_overrides[appexport_routes.get_task_deferrer] = lambda: deferrer
        return TestClient(app), calls

    return make_client, owner, stranger, item.id, Session


def test_post_app_export_requires_flag_enabled(env, monkeypatch):
    make_client, _owner, _stranger, item_id, _Session = env
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    client, _calls = make_client()
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 404


def test_post_app_export_creates_job_and_returns_202(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 202
    assert "jobId" in response.json()
    assert len(calls) == 1


def test_post_app_export_denies_user_without_read_access(env):
    make_client, _owner, stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    client.app.dependency_overrides[get_current_user_optional] = lambda: stranger
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 404


def test_post_app_export_rejects_invalid_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "connected"})
    assert response.status_code == 422  # SP-18a only supports "static"


def test_get_app_export_job_reports_status(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/app-exports", json={"itemId": item_id, "mode": "static"}).json()
    response = client.get(f"/app-exports/jobs/{created['jobId']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["resultUrl"] is None


def test_get_app_export_job_done_status_includes_result_url(env):
    make_client, owner, _stranger, item_id, Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/app-exports", json={"itemId": item_id, "mode": "static"}).json()
    job_id = created["jobId"]
    with Session() as s:
        appexport_repo.mark_running(s, job_id=job_id)
        appexport_repo.mark_done(s, job_id=job_id, result_key=f"appexports/{job_id}.zip")
        s.commit()
    response = client.get(f"/app-exports/jobs/{job_id}")
    body = response.json()
    assert body["status"] == "done"
    assert body["resultUrl"] == f"https://minio.test/geostudio-appexports/appexports/{job_id}.zip"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write `routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'export d'app (SP-18a) — montées uniquement quand
CORE_APPEXPORT_ENABLED est actif, même patron que app.export.routes."""
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.appexport import repository as appexport_repo
from app.appexport.jobs import build_app_export_task
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_SUPPORTED_MODES = {"static"}  # "connected"/"standalone" arrivent en SP-18b/c


class CreateAppExportRequest(BaseModel):
    itemId: str
    mode: str


class CreateAppExportResponse(BaseModel):
    jobId: str


class AppExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None


def _require_export_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")


def get_appexports_bucket() -> str:
    return os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        build_app_export_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/app-exports", response_model=CreateAppExportResponse, status_code=202)
def create_app_export_route(
    body: CreateAppExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> CreateAppExportResponse:
    if body.mode not in _SUPPORTED_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {sorted(_SUPPORTED_MODES)}")
    _require_export_read_access(session, user=user, item_id=body.itemId)
    job = appexport_repo.create_job(session, tenant_id=user.tenant_id, item_id=body.itemId, user_id=user.id, mode=body.mode)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="appexport.create", object_type="app_export_job", object_id=job.id,
        payload={"itemId": body.itemId, "mode": body.mode},
    )
    session.commit()  # commit avant de déférer : même raison que export_routes/run_pipeline_route
    defer_task(job.id, user.tenant_id)
    return CreateAppExportResponse(jobId=job.id)


@router.get("/app-exports/jobs/{job_id}", response_model=AppExportJobStatus)
def get_app_export_job_route(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_appexports_bucket),
) -> AppExportJobStatus:
    job = appexport_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="app export job not found")
    _require_export_read_access(session, user=user, item_id=job.item_id)
    result_url = None
    if job.status == "done" and job.result_key:
        result_url = generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)
    return AppExportJobStatus(id=job.id, status=job.status, resultUrl=result_url, error=job.error)
```

- [ ] **Step 4: Wire into `app/main.py`**

Add the import near the other export-family imports, mount conditionally,
and add the S3 bucket dependency override, mirroring `export_routes`
exactly:

```python
from app.appexport import routes as appexport_routes
```
```python
    if is_appexport_enabled():
        app.include_router(appexport_routes.router)
```
```python
        s3_appexports_bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        app.dependency_overrides[appexport_routes.get_appexports_bucket] = lambda: s3_appexports_bucket
```

Also import `is_appexport_enabled` alongside the other `is_*_enabled`
imports at the top of `app/main.py`.

- [ ] **Step 5: Add `appExportEnabled` to instance info**

In `core/app/instance/routes.py`, add a line next to the existing flags:

```python
        "appExportEnabled": is_appexport_enabled(),
```

(import `is_appexport_enabled` there too).

- [ ] **Step 6: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the full core suite for regressions**

Run: `cd core && uv run pytest -q`
Expected: all pass (existing counts + new tests from Tasks 1–8), no
collection errors.

- [ ] **Step 8: Commit**

```bash
git add core/app/appexport/routes.py core/app/main.py core/app/instance/routes.py \
  core/tests/test_appexport_routes.py
git commit -m "feat(core): POST/GET /app-exports routes (SP-18a)"
```

---

### Task 9: shell — `StaticItemClient` + export entry

**Files:**
- Create: `shell/src/staticExport/StaticItemClient.ts`
- Create: `shell/src/staticExport/entry.tsx`
- Create: `shell/index.export.html`
- Test: `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Consumes: `ItemClient` (interface, `shell/src/api/types.ts`), `AppConfig`.
- Produces: `createStaticItemClient(config: AppConfig): ItemClient`. The
  bundled config's `"features"`-type sources have already been rewritten to
  `"static"` by the core (Task 5) — this client needs no bespoke data
  lookup, it reuses the exact same `"static"` branch shape the live
  `createItemClient` already has.

- [ ] **Step 1: Write the failing test**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig } from "../api/types";

function config(): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [
      { id: "s1", type: "static", service: "core", layer: "", query: { records: [{ id: 1, properties: { name: "Alpha" } }] } },
    ],
    messages: [], pages: [{ id: "p1", name: "P1", layout: { type: "grid", breakpoints: {}, items: [] }, onEnter: [] }],
    navigationMode: "tabs", variables: [],
  } as unknown as AppConfig;
}

describe("StaticItemClient", () => {
  it("getAppConfig returns the embedded config", async () => {
    const client = createStaticItemClient(config());
    const result = await client.getAppConfig("any-pk");
    expect(result.kind).toBe("app");
    expect(result.pages).toHaveLength(1);
  });

  it("queryDataSource resolves static records from the embedded query", async () => {
    const client = createStaticItemClient(config());
    const records = await client.queryDataSource(config().dataSources[0]);
    expect(records).toEqual([{ id: 1, properties: { name: "Alpha" } }]);
  });

  it("createFeature throws an explicit unsupported error", async () => {
    const client = createStaticItemClient(config());
    await expect(client.createFeature("col1", { properties: {} })).rejects.toThrow(/statique/i);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/staticExport/StaticItemClient.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `StaticItemClient.ts`**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Implémentation "zéro backend" d'ItemClient pour le mode Statique (SP-18a).
// Le cœur a déjà réécrit toute DataSource "features" en "static" avant
// l'export (core/app/appexport/freeze.py) — queryDataSource n'a donc besoin
// que de la même branche "static" que createItemClient (itemClient.ts)
// utilise déjà en direct, jamais de réseau.
import type { AppConfig, DataRecord, DataSource, ItemClient } from "./types-reexport";

const UNSUPPORTED = "Non disponible dans un export statique (aucun backend).";

function unsupported<T = never>(): Promise<T> {
  return Promise.reject(new Error(UNSUPPORTED));
}

export function createStaticItemClient(config: AppConfig): ItemClient {
  return {
    async getAppConfig() {
      return config;
    },
    async getPublicAppConfig() {
      return config;
    },
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      return (source.query.records as DataRecord[] | undefined) ?? [];
    },
    featuresUrl() {
      throw new Error(UNSUPPORTED);
    },
    async createFeature() { return unsupported(); },
    async updateFeature() { return unsupported(); },
    async deleteFeature() { return unsupported(); },
    async exportDataSource() { return unsupported(); },
    async runAnalyticsSql() { return unsupported(); },
    // Le reste de l'interface ItemClient (catalogue, partage, harvest,
    // ingestion, 3D, MCP…) n'a aucun sens sans backend — chaque méthode
    // rejette explicitement plutôt que d'être omise (le type ItemClient est
    // large, cf. plan §research ; omettre une méthode romprait le contrat
    // TypeScript). Générées mécaniquement à l'implémentation (Task 9, Step
    // 3) par copie du even la liste de méthodes d'ItemClient (types.ts)
    // vers `async methodName() { return unsupported(); }`.
  } as unknown as ItemClient;
}
```

> Note for the implementer: `ItemClient` (`shell/src/api/types.ts`) has ~60
> methods (full list surfaced during planning — catalogue, sharing, layers,
> extensions, per-kind config CRUD, uploads, 3D, MCP). Write out every
> remaining method as `async methodName(..._args: unknown[]) { return
> unsupported(); }` rather than the `as unknown as ItemClient` cast shown
> above — the cast is a planning-time placeholder to keep this plan
> readable; the real file must satisfy the interface without an escape
> hatch, so TypeScript catches any method this plan's author misses. Import
> `ItemClient`/`AppConfig`/`DataSource`/`DataRecord` from `../api/types`
> directly (the `types-reexport` name above is a planning artifact, not a
> real file — fix the import in Step 3).

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/staticExport/StaticItemClient.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the export entry component**

```tsx
// shell/src/staticExport/entry.tsx
// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig } from "../api/types";
import "../index.css";

registerBuiltinWidgets();

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("export entry: #root introuvable");
  const response = await fetch("./geostudio-app-config.json");
  if (!response.ok) throw new Error("export entry: geostudio-app-config.json introuvable");
  const config = (await response.json()) as AppConfig;
  const client = createStaticItemClient(config);
  createRoot(root).render(
    <StrictMode>
      <ItemClientProvider client={client}>
        <div className="h-screen w-screen">
          <AppRenderer config={config} mode="runtime" pageId={config.pages[0]?.id} />
        </div>
      </ItemClientProvider>
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  if (root) root.textContent = `Erreur de chargement : ${(err as Error).message}`;
});
```

- [ ] **Step 6: Write `shell/index.export.html`**

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <title>GeoStudio — application exportée</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/staticExport/entry.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Run the shell unit test suite for regressions**

Run: `cd shell && npm run test`
Expected: all pass (existing counts + 3 new).

- [ ] **Step 8: Commit**

```bash
git add shell/src/staticExport shell/index.export.html
git commit -m "feat(shell): StaticItemClient + static export entry (SP-18a)"
```

---

### Task 10: Vite export-runtime build + Docker/compose wiring

**Files:**
- Create: `shell/vite.export.config.ts`
- Modify: `shell/package.json`
- Create: `deploy/appexport-runtime-builder/Dockerfile`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `npm run build:export-runtime` in `shell/`, output at
  `shell/dist-export/{index.export.html,assets/*}` — this is the "prebuilt,
  generic, app-agnostic" runtime the core job (Task 6/7) copies into every
  export's zip, never rebuilt per export.

- [ ] **Step 1: Write `vite.export.config.ts`**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Config Vite séparée de vite.config.ts (config combinée Vite+Vitest) : ce
// build ne doit jamais dépendre de la config de test, et produit un
// artefact générique (pas lié à une app précise) rebâti une seule fois à
// l'image, jamais par export (SP-18a, plan §Architecture).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist-export",
    rollupOptions: {
      input: resolve(__dirname, "index.export.html"),
    },
  },
});
```

- [ ] **Step 2: Add the npm script**

In `shell/package.json`'s `"scripts"`:

```json
    "build:export-runtime": "vite build --config vite.export.config.ts",
```

- [ ] **Step 3: Build it locally to verify the artifact shape**

Run: `cd shell && npm run build:export-runtime`
Expected: `dist-export/index.export.html` and `dist-export/assets/*.js`/
`*.css` exist. Confirm `index.export.html`'s script tag references a hashed
asset path under `assets/` (Vite's standard output) — this is what Task 6's
`bundler.py` copies verbatim.

- [ ] **Step 4: Write the builder Dockerfile**

```dockerfile
# deploy/appexport-runtime-builder/Dockerfile
# Bâtit une fois le runtime d'export statique générique (shell/dist-export)
# et le copie dans un volume Docker partagé avec `worker` — jamais rebâti
# par export (SP-18a, plan §Architecture). Contexte = racine du dépôt (pas
# ./shell) : c'est le seul service de la stack dont c'est le cas, pour
# pouvoir COPY shell/ sans changer le contexte des autres services Node.
FROM node:20-slim
WORKDIR /build
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
CMD ["sh", "-c", "mkdir -p /export-runtime && cp -r dist-export/* /export-runtime/ && echo 'export runtime built'"]
```

- [ ] **Step 5: Wire into `docker-compose.yml`**

Add a new named volume to the top-level `volumes:` block:

```yaml
  appexport-runtime:
```

Add a new one-shot service (near `qgis-worker`/`export-worker`):

```yaml
  # Bâtit une fois le runtime d'export statique générique et le dépose dans
  # le volume `appexport-runtime`, consommé par `worker` (SP-18a). Tourne
  # une seule fois par `docker compose up` (aucun `restart:`), `worker`
  # attend sa complétion via `condition: service_completed_successfully`.
  appexport-runtime-builder:
    build:
      context: .
      dockerfile: deploy/appexport-runtime-builder/Dockerfile
    volumes:
      - appexport-runtime:/export-runtime
```

In the `worker` service: add the volume mount, `depends_on` condition, and
env vars, and extend the queue list:

```yaml
  worker:
    build: ./core
    command: >
      sh -c "python -m scripts.ensure_procrastinate_schema &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc,etl,tileset3d,terrain3d,appexport"
    environment:
      # … (existing vars unchanged) …
      CORE_APPEXPORT_ENABLED: ${CORE_APPEXPORT_ENABLED:-false}
      APPEXPORT_RUNTIME_DIR: /export-runtime
      S3_APPEXPORTS_BUCKET: geostudio-appexports
    volumes:
      - etl-scratch:/scratch
      - appexport-runtime:/export-runtime:ro
    depends_on:
      pgbouncer:
        condition: service_started
      minio:
        condition: service_started
      appexport-runtime-builder:
        condition: service_completed_successfully
```

(`depends_on`'s existing plain-list form `[pgbouncer, minio]` must become
the long form above to mix a `service_completed_successfully` condition
with the others — Compose doesn't allow mixing short and long forms in one
`depends_on` block.)

In the `core` service: add `CORE_APPEXPORT_ENABLED` next to the other
capability flags (needed so `POST/GET /app-exports` mount):

```yaml
      CORE_APPEXPORT_ENABLED: ${CORE_APPEXPORT_ENABLED:-false}
```

- [ ] **Step 6: Verify the compose config parses**

Run: `docker compose config --quiet`
Expected: no errors (validates YAML + the new `depends_on` long form).

- [ ] **Step 7: Commit**

```bash
git add shell/vite.export.config.ts shell/package.json \
  deploy/appexport-runtime-builder/Dockerfile docker-compose.yml
git commit -m "feat(deploy): build+bake export-runtime bundle for app export (SP-18a)"
```

---

### Task 11: shell `ItemClient` wiring — `createAppExport`/`getAppExportJob`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `core/openapi.json` (regenerated, not hand-edited)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated)

**Interfaces:**
- Produces (on `ItemClient`): `createAppExport(itemId: string, mode:
  "static"): Promise<{ jobId: string }>`, `getAppExportJob(itemId: string,
  jobId: string): Promise<AppExportJobStatus>`. New types `AppExportMode =
  "static"`, `AppExportJobStatus = { id: string; status: string; resultUrl:
  string | null; error: string | null }`. `InstanceInfo` gains
  `appExportEnabled: boolean`.

- [ ] **Step 1: Add the types**

In `shell/src/api/types.ts`, near `ExportJob`/`InstanceInfo`:

```typescript
export type AppExportMode = "static";

export type AppExportJobStatus = {
  id: string;
  status: string;
  resultUrl: string | null;
  error: string | null;
};
```

And extend `InstanceInfo`:

```typescript
export type InstanceInfo = {
  readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean;
  appExportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean;
};
```

Add to the `ItemClient` interface (near `createExport`/`getExportJob`):

```typescript
  createAppExport(itemId: string, mode: AppExportMode): Promise<{ jobId: string }>;
  getAppExportJob(itemId: string, jobId: string): Promise<AppExportJobStatus>;
```

- [ ] **Step 2: Implement in `itemClient.ts`**

Near the existing `createExport`/`getExportJob` implementations:

```typescript
    async createAppExport(itemId: string, mode: AppExportMode): Promise<{ jobId: string }> {
      const data = await request<{ jobId: string }>("POST", "/app-exports", { itemId, mode });
      return data;
    },

    async getAppExportJob(_itemId: string, jobId: string): Promise<AppExportJobStatus> {
      return request<AppExportJobStatus>("GET", `/app-exports/jobs/${jobId}`);
    },
```

(`_itemId` unused by the request itself — kept in the signature because the
server-side access check is keyed off the job's own `item_id`, but the
call-site UI needs a stable, explicit association between panel and item;
matches `getExportJob`'s shell-side call convention of always being invoked
alongside a known `itemId` prop.)

- [ ] **Step 3: Regenerate the OpenAPI schema + TS types**

Run: `cd core && uv run python -c "import json; from app.main import
create_app; print(json.dumps(create_app().openapi()))" >
openapi.json` (or whatever the existing regen script is — confirm via
`grep -rn "openapi.json" core/scripts/ core/Makefile 2>/dev/null`; this
step exists because CLAUDE.md flags "OpenAPI/TS jamais régénérés" as a
**4-times-repeated** class of bug across prior SPs — do not skip it), then
`cd shell && npm run gen:api-types`
Expected: `core/openapi.json` and
`shell/src/api/generated/core-schema.d.ts` both show diffs including the
new `/app-exports` paths.

- [ ] **Step 4: Run `npm run build` (includes `tsc --noEmit`)**

Run: `cd shell && npm run build`
Expected: no type errors (confirms `StaticItemClient`'s full method
coverage from Task 9 and the new `ItemClient` methods here are consistent).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts \
  core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(shell): ItemClient.createAppExport/getAppExportJob (SP-18a)"
```

---

### Task 12: builder UI — `AppExportPanel` + write-widget warning

**Files:**
- Create: `shell/src/builder/appexport/collectWidgetTypes.ts`
- Create: `shell/src/builder/appexport/AppExportPanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/appexport/collectWidgetTypes.test.ts`,
  `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Interfaces:**
- Consumes: `AppConfig`, `useItemClient()`, `useInstanceInfo()` (existing
  hooks).
- Produces: `collectWidgetTypes(config: AppConfig): Set<string>` (top-level
  widget types only — see plan's documented nested-container gap),
  `<AppExportPanel itemId={string} config={AppConfig} />`.

- [ ] **Step 1: Write the failing test for `collectWidgetTypes`**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { collectWidgetTypes } from "./collectWidgetTypes";
import type { AppConfig } from "../../api/types";

function config(itemsByPage: string[][]): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [], messages: [], navigationMode: "tabs", variables: [],
    pages: itemsByPage.map((types, pi) => ({
      id: `p${pi}`, name: `P${pi}`, onEnter: [],
      layout: {
        type: "grid", breakpoints: {},
        items: types.map((t, i) => ({ id: `w${pi}-${i}`, widget: t, x: 0, y: i, w: 4, h: 2, props: {} })),
      },
    })),
  } as unknown as AppConfig;
}

describe("collectWidgetTypes", () => {
  it("collects distinct widget types across all pages", () => {
    const types = collectWidgetTypes(config([["text", "map"], ["text", "form"]]));
    expect([...types].sort()).toEqual(["form", "map", "text"]);
  });

  it("returns an empty set for a config with no widgets", () => {
    expect(collectWidgetTypes(config([[]]))).toEqual(new Set());
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/appexport/collectWidgetTypes.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `collectWidgetTypes.ts`**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Scan top-level uniquement (pas de récursion dans tabs/modal/drawer — leur
// contenu vit dans LayoutItem.props: dict côté serveur, invisible à un scan
// typé ; cf. plan §Global Constraints, gap documenté non bloquant).
import type { AppConfig } from "../../api/types";

export function collectWidgetTypes(config: AppConfig): Set<string> {
  const types = new Set<string>();
  for (const page of config.pages) {
    for (const item of page.layout.items) {
      types.add(item.widget);
    }
  }
  return types;
}

export const WRITE_CAPABLE_WIDGET_TYPES = new Set(["form"]);
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/collectWidgetTypes.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test for `AppExportPanel`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppExportPanel } from "./AppExportPanel";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";

function config(withForm = false): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [], messages: [], navigationMode: "tabs", variables: [],
    pages: [{
      id: "p1", name: "P1", onEnter: [],
      layout: { type: "grid", breakpoints: {}, items: withForm ? [{ id: "w1", widget: "form", x: 0, y: 0, w: 4, h: 2, props: {} }] : [] },
    }],
  } as unknown as AppConfig;
}

function makeClient(overrides: Partial<ItemClient>): ItemClient {
  return overrides as ItemClient;
}

describe("AppExportPanel", () => {
  it("triggers export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "static");
  });

  it("warns before export when the config contains a form widget", async () => {
    const client = makeClient({ createAppExport: vi.fn(), getAppExportJob: vi.fn() });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config(true)} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
    expect(client.createAppExport).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: FAIL (module not found)

- [ ] **Step 7: Write `AppExportPanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
// Même patron de poll que shell/src/builder/print/ExportPanel.tsx (SP-17a) :
// boucle récursive manuelle via le client, jamais un refetchInterval
// react-query — cf. plan Global Constraints (superpowers writing-plans).
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { AppConfig, AppExportJobStatus, AppExportMode } from "../../api/types";
import { Button } from "../../ui/button";
import { collectWidgetTypes, WRITE_CAPABLE_WIDGET_TYPES } from "./collectWidgetTypes";

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 200;

export function AppExportPanel({ itemId, config }: { itemId: string; config: AppConfig }) {
  const client = useItemClient();
  const [job, setJob] = useState<AppExportJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [showWriteWarning, setShowWriteWarning] = useState(false);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  async function poll(jobId: string, attempt = 0): Promise<void> {
    if (!mountedRef.current) return;
    const latest = await client.getAppExportJob(itemId, jobId);
    if (!mountedRef.current) return;
    setJob(latest);
    if (latest.status !== "pending" && latest.status !== "running") return;
    if (attempt + 1 >= MAX_POLL_ATTEMPTS) {
      setError("Export toujours en cours, réessayer plus tard.");
      return;
    }
    await new Promise<void>((resolve) => {
      timerRef.current = setTimeout(resolve, POLL_INTERVAL_MS);
    });
    if (!mountedRef.current) return;
    await poll(jobId, attempt + 1);
  }

  async function startExport(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) => WRITE_CAPABLE_WIDGET_TYPES.has(t));
    if (hasWriteWidget) {
      setShowWriteWarning(true);
      return;
    }
    await runExport(mode);
  }

  async function runExport(mode: AppExportMode) {
    setShowWriteWarning(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createAppExport(itemId, mode);
      await poll(jobId);
    } catch {
      if (mountedRef.current) setError("Échec de l'export.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={running} onClick={() => startExport("static")}>
          Exporter
        </Button>
        <Button size="sm" variant="outline" disabled={running} onClick={() => startExport("static")}>
          Statique
        </Button>
      </div>
      {showWriteWarning && (
        <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
          <p>
            Cette app contient un widget Formulaire — toute écriture sera
            désactivée dans l&apos;export statique faute de backend.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => runExport("static")}>Exporter quand même</Button>
            <Button size="sm" variant="outline" onClick={() => setShowWriteWarning(false)}>Annuler</Button>
          </div>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-blue-600 underline">
          Télécharger le bundle
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert" className="text-sm text-red-600">{error ?? job?.error ?? "Échec de l'export."}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: PASS (2 tests). Note the first test's two-button layout ("Exporter"
opens/no-ops today since there's only one mode in SP-18a) — adjust to a
single "Exporter (statique)" button if the two-button placeholder from Step
7 reads awkwardly in review; the mode picker becomes meaningful once SP-18b
adds "Connecté".

- [ ] **Step 9: Mount in `AppBuilderPage.tsx`**

In `shell/src/pages/AppBuilderPage.tsx`, add the import and gate on
`useInstanceInfo()`, placed after the "Impression" section:

```tsx
import { AppExportPanel } from "../builder/appexport/AppExportPanel";
import { useInstanceInfo } from "../api/hooks";
```

Inside the component:
```tsx
  const instanceQuery = useInstanceInfo();
  const appExportEnabled = instanceQuery.data?.appExportEnabled === true;
```

In the sidebar, after the `PrintLayoutPanel` block:
```tsx
              {appExportEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Export standalone</p>
                  <AppExportPanel itemId={pk} config={draft} />
                </>
              )}
```

- [ ] **Step 10: Run the shell unit test suite for regressions**

Run: `cd shell && npm run test`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add shell/src/builder/appexport shell/src/pages/AppBuilderPage.tsx
git commit -m "feat(shell): AppExportPanel — trigger + poll + write-widget warning (SP-18a)"
```

---

### Task 13: E2E — static bundle served with zero GeoStudio backend

**Files:**
- Create: `shell/e2e/static-export.spec.ts`

**Interfaces:**
- Consumes: the existing Playwright E2E harness (`shell/playwright.config.ts`,
  `VITE_AUTH_MODE=mock`), plus Node's `http-server`-equivalent (spawn a
  plain static file server, no existing precedent in this repo per plan
  research — this task introduces it).

- [ ] **Step 1: Write the E2E spec**

This test must prove the spec's §5.1 requirement literally: **no GeoStudio
core in the loop at all** for the final assertion. It builds a small config
by hand (bypassing the builder UI, since the guard/freeze path is already
covered by core tests in Tasks 4–8), serves it via `createStaticItemClient`
mounted on a real second HTTP server, and asserts against that server —
never against `https://core.test`.

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Sert shell/dist-export/ (bâti par `npm run build:export-runtime`, Task 10)
// + un geostudio-app-config.json fabriqué à la main pour ce test — aucune
// route https://core.test n'est jamais enregistrée dans ce fichier (à la
// différence de tous les autres specs e2e/*.ts qui appellent mockCore(page)) :
// c'est la preuve que le mode Statique n'a besoin d'aucun backend.
const DIST_EXPORT = path.resolve(__dirname, "../dist-export");

const FROZEN_CONFIG = {
  kind: "app", theme: {}, navigationMode: "tabs", variables: [], messages: [],
  dataSources: [
    { id: "s1", type: "static", service: "core", layer: "", query: { records: [{ id: 1, properties: { name: "Alpha" } }] } },
  ],
  pages: [{
    id: "p1", name: "P1", onEnter: [],
    layout: { type: "grid", breakpoints: {}, items: [{ id: "w1", widget: "table", x: 0, y: 0, w: 6, h: 4, props: { dataSourceId: "s1" } }] },
  }],
};

async function startStaticServer(): Promise<{ server: Server; url: string }> {
  const server = createServer(async (req, res) => {
    if (req.url === "/geostudio-app-config.json") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(FROZEN_CONFIG));
      return;
    }
    const filePath = req.url === "/" || !req.url ? "/index.export.html" : req.url;
    try {
      const body = await readFile(path.join(DIST_EXPORT, filePath.replace(/^\//, "")));
      const contentType = filePath.endsWith(".js") ? "application/javascript" : filePath.endsWith(".css") ? "text/css" : "text/html";
      res.setHeader("Content-Type", contentType);
      res.end(body);
    } catch {
      res.statusCode = 404;
      res.end("not found");
    }
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return { server, url: `http://127.0.0.1:${port}` };
}

test("static export bundle renders with zero GeoStudio backend", async ({ page }) => {
  const { server, url } = await startStaticServer();
  try {
    await page.goto(url);
    await expect(page.getByText("Alpha")).toBeVisible({ timeout: 10_000 });
  } finally {
    server.close();
  }
});
```

- [ ] **Step 2: Build the export-runtime fixture the test depends on**

Run: `cd shell && npm run build:export-runtime`
Expected: `dist-export/index.export.html` exists (this test reads it
directly — add a `pretest` note in the E2E README or a `beforeAll` guard
that skips with a clear message if `dist-export` is absent, mirroring how
`@pytest.mark.playwright`-style optional-dependency specs in this repo skip
cleanly rather than fail opaquely).

- [ ] **Step 3: Run the E2E spec**

Run: `cd shell && npx playwright test e2e/static-export.spec.ts`
Expected: PASS. If the `table` widget requires a `pkColumn`/`hasGeometry`
that `StaticItemClient` doesn't provide (Task 9's client only implements
`getAppConfig`/`queryDataSource`, not `getDatasetConfig`/
`getCollectionSchema` since no `DataSource` in a persisted config ever
carries `datasetId` — see plan's Global Constraints), swap the `table`
widget for `text`/`list` in `FROZEN_CONFIG` if `table` render fails without
those two calls; confirm which builtin widgets tolerate their absence by
reading `shell/src/builder/widgets/data.tsx` before finalizing this step.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/static-export.spec.ts
git commit -m "test(e2e): static export bundle runs with zero backend (SP-18a)"
```

---

### Task 14: full regression pass + branch review

- [ ] **Step 1: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: all pass, including the 606+-and-growing pre-existing count plus
this plan's ~25 new tests.

- [ ] **Step 2: Run the full shell suite**

Run: `cd shell && npm run test && npm run build && npm run e2e`
Expected: all pass.

- [ ] **Step 3: Run import-linter**

Run: `cd core && uv run lint-imports` (or the project's actual invocation —
confirm the exact command via `grep -rn "lint-imports\|importlinter"
core/pyproject.toml core/Makefile 2>/dev/null`)
Expected: no violations (confirms `app.appexport`'s layer placement, Task 3).

- [ ] **Step 4: Request code review**

Use `superpowers:requesting-code-review` before merging — this plan's
author already flagged several signature/shape assumptions (Tasks 4, 5, 9)
that must be confirmed against real code, not just this plan's guesses;
review is the checkpoint to catch any that slipped through.

---

## Self-Review Notes (for the plan author)

- **Spec coverage:** §2.3 (mode Statique) — Tasks 1–13. §3 (mécanisme
  commun: trigger/build/guard) — Tasks 4, 7, 8, 12 (the "build only widgets
  actually used" clause is satisfied by construction: the export-runtime
  bundle only ever contains `registerBuiltinWidgets()`'s fixed set, and the
  guard rejects anything else, so there's never a per-export bundle-size
  concern to solve). §4 hors périmètre — respected (no RLS/private data
  export, no writes in Statique, no auto-sync, no CI auto-deploy, no
  GeoStudio-hosted exports, no 3D/print widgets — the guard's
  `_SUPPORTED_WIDGET_TYPES` already excludes `tiles3d`/print-only concerns
  since those aren't registered by `registerBuiltinWidgets()` as page
  widgets in the first place). §5.1 (Statique E2E) — Task 13. §5.4
  (non-regression) — Task 14. §6 open questions — **format**: resolved as
  zip (Task 6/8, mirrors SP-17a). **Mini-serveur location**: N/A to SP-18a
  (Autoporté is SP-18c). **Calendar position**: resolved — this plan starts
  immediately, SP-11 already shipped.
- **Not covered by this plan (explicitly deferred, tracked for SP-18b/c or
  a fast-follow):** Mode Connecté, Mode Autoporté; `"statistics"`-type
  DataSource freezing; third-party WC extension widget bundling; nested
  container-widget (tabs/modal/drawer) guard scanning.
- **Placeholder scan:** Task 9's `StaticItemClient.ts` code block
  intentionally shows a partial implementation with an explicit inline note
  telling the implementer to complete the remaining ~55 pass-through
  methods mechanically — flagged there rather than silently treated as
  finished, since spelling out every one of ~60 near-identical one-liners
  here would make this plan unreadable without adding real information.
  Task 4/5's tests carry an explicit "confirm exact kwargs before finalizing"
  note for the same reason: this plan was written from function
  signatures observed during research, not a guarantee every keyword-arg
  name is byte-exact — flagged at the point of risk rather than glossed
  over.
- **Type consistency:** `AppExportJobStatus` (shell, Task 11) matches
  `AppExportJobStatus` (core Pydantic response model, Task 8) field-for-field
  (`id`, `status`, `resultUrl`/`result_url` via FastAPI's camelCase
  response, `error`). `AppExportMode` (shell) = `_SUPPORTED_MODES` (core,
  currently `{"static"}`) — Task 8's 422 test locks this in.
