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

