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

