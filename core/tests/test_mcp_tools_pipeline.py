# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # CORE_ETL_ENABLED est lu par create_app()/register_tools() à la
    # construction (pas par requête) — les appelants doivent le positionner
    # via monkeypatch.setenv AVANT que cette fixture construise l'app.
    # D'où une fixture-fabrique plutôt qu'un TestClient figé.
    def _build(etl_enabled: bool):
        monkeypatch.setenv("CORE_ETL_ENABLED", "true" if etl_enabled else "false")
        engine = make_engine(db_url)
        init_db(engine)
        Session = make_session_factory(engine)
        with Session() as setup_session:
            tenant = get_or_create_default_tenant(setup_session)
            get_or_create_user(
                setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
                username="mockuser", email=None, first_name="Mock", last_name="User",
            )
            setup_session.commit()
        app = create_app()

        def override_session():
            with request_scoped_session(Session) as session:
                yield session

        app.dependency_overrides[db.get_session] = override_session
        return TestClient(app, base_url="http://localhost:8200")

    return _build


def _init_and_list_tools(test_client) -> set[str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}},
    }, headers=headers)
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}
    test_client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                     headers=session_headers)
    list_response = test_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    }, headers=session_headers)
    body_line = next(
        line for line in list_response.text.splitlines() if line.startswith("data: ")
    )
    payload = json.loads(body_line.removeprefix("data: "))
    return {tool["name"] for tool in payload["result"]["tools"]}


def test_pipeline_tools_absent_when_etl_disabled(app_client):
    client = app_client(etl_enabled=False)
    with client:
        names = _init_and_list_tools(client)
    assert "create_pipeline" not in names
    assert "run_pipeline" not in names
    assert "explain_pipeline" not in names


def test_pipeline_tools_present_when_etl_enabled(app_client):
    client = app_client(etl_enabled=True)
    with client:
        names = _init_and_list_tools(client)
    assert {"create_pipeline", "run_pipeline", "explain_pipeline"} <= names
