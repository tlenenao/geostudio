### Task 3: Table `export_jobs` + repository

**Files:**
- Create: `core/app/export/__init__.py` (vide)
- Create: `core/app/export/models.py`
- Create: `core/app/export/repository.py`
- Test: `core/tests/test_export_repository.py`

**Interfaces:**
- Produces: modèle SQLAlchemy `ExportJob` (table `export_jobs`) : `id: str` (PK, `uuid4().hex`), `tenant_id: str`, `item_id: str`, `user_id: str`, `format: str`, `status: str` (défaut `"pending"`), `error: str | None`, `result_key: str | None`, `created_at`, `started_at: datetime | None`, `finished_at: datetime | None`.
- Produces (repository) : `create_job(session, *, tenant_id, item_id, user_id, format) -> ExportJob`, `mark_running(session, *, job_id) -> None`, `mark_done(session, *, job_id, result_key) -> None`, `mark_error(session, *, job_id, error) -> None`, `get_job(session, *, tenant_id, job_id) -> ExportJob | None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_export_repository.py
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.tenants.repository import get_or_create_default_tenant


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_create_job_starts_pending():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    assert job.status == "pending"
    assert job.error is None
    assert job.result_key is None
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched is not None
    assert fetched.format == "png"


def test_mark_running_then_done():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="pdf")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_done(session, job_id=job.id, result_key="exports/item-1/x.pdf")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "done"
    assert fetched.result_key == "exports/item-1/x.pdf"
    assert fetched.started_at is not None
    assert fetched.finished_at is not None


def test_mark_error_never_leaves_status_running():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_error(session, job_id=job.id, error="render timeout")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert fetched.error == "render timeout"


def test_get_job_scoped_to_tenant():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    assert export_repo.get_job(session, tenant_id="other-tenant", job_id=job.id) is None
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export'`

- [ ] **Step 3: Implémenter**

`core/app/export/__init__.py` : fichier vide (juste le header ne s'applique pas à un `__init__.py` vide dans ce dépôt — vérifier `core/app/alerts/__init__.py` : s'il est vide, laisser `core/app/export/__init__.py` vide aussi, sans contenu).

```python
# core/app/export/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

```python
# core/app/export/repository.py
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.export.models import ExportJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(session: Session, *, tenant_id: str, item_id: str, user_id: str, format: str) -> ExportJob:
    job = ExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        format=format, status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> ExportJob | None:
    return session.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = _now()
    session.flush()


def mark_done(session: Session, *, job_id: str, result_key: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.result_key = result_key
    job.finished_at = _now()
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error = error
    job.finished_at = _now()
    session.flush()
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_repository.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/export/__init__.py core/app/export/models.py core/app/export/repository.py core/tests/test_export_repository.py
git commit -m "feat(core): SP-17a — table export_jobs + repository"
```

---

