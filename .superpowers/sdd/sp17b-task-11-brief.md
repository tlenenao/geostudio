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

