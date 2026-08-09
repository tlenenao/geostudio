# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.reports import repository as reports_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
            username="mockuser", email=None, first_name="Mock", last_name="User",
        )
        setup_session.commit()
        tenant_id, user_id = tenant.id, mock_user.id

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    from app.db import get_session
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app, base_url="http://localhost:8200")
    return client, Session, tenant_id, user_id


def _seed_report_schedule(Session, *, tenant_id, owner_id, with_run=True):
    with Session() as s:
        report_item = items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=owner_id, resource_type="report", title="Weekly report",
        )
        report_config = BuilderConfig.model_validate({
            "kind": "report",
            "report": {
                "bookmarkItemId": "bookmark-1",
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        })
        configs_repo.create_config(s, report_config, item_id=report_item.id, tenant_id=tenant_id)
        if with_run:
            reports_repo.create_run(
                s, tenant_id=tenant_id, report_item_id=report_item.id, export_job_id="job-1",
            )
        s.commit()
        return report_item.id


def test_explain_report_schedule_returns_the_schedule_shape(app_client):
    client, Session, tenant_id, user_id = app_client
    report_item_id = _seed_report_schedule(Session, tenant_id=tenant_id, owner_id=user_id)

    with client:
        result = call_tool(client, "explain_report_schedule", {"reportScheduleId": report_item_id})

    assert result["title"] == "Weekly report"
    assert result["bookmarkItemId"] == "bookmark-1"
    assert result["channels"] == ["webhook"]
    assert result["refreshPolicy"]["cron"] == "0 8 * * MON"
    assert result["lastRunAt"] is not None


def test_explain_report_schedule_404s_for_an_unreadable_schedule(app_client):
    client, Session, tenant_id, user_id = app_client
    with client:
        error_text = call_tool_expecting_error(client, "explain_report_schedule", {"reportScheduleId": "does-not-exist"})
    assert "report schedule not found" in error_text
