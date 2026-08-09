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
