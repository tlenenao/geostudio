# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.mcp.tools import READ_ONLY_TOOLS
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

READ_ONLY_MESSAGE = "Mode démo : lecture seule, écritures désactivées."


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    # create_app() construit son propre engine depuis DATABASE_URL (app/main.py)
    # et les outils MCP ferment sur *ce* session_factory — pas celui construit
    # ici. Un ":memory:" nu donnerait deux bases déconnectées ; on route donc
    # les deux par le même fichier sur disque (même patron que
    # test_mcp_tools_create.py, SP-7).
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

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.mock_user = mock_user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def call_tool(test_client, name: str, arguments: dict) -> dict:
    result = call_tool_raw(test_client, name, arguments)
    if result.get("isError"):
        raise AssertionError(f"tool {name} errored: {result['content'][0]['text']}")
    return json.loads(result["content"][0]["text"])


def call_tool_expecting_error(test_client, name: str, arguments: dict) -> str:
    result = call_tool_raw(test_client, name, arguments)
    assert result.get("isError"), f"expected tool {name} to error, got: {result}"
    return result["content"][0]["text"]


def call_tool_raw(test_client, name: str, arguments: dict) -> dict:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=headers,
    )
    assert init_response.status_code == 200
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}

    notify_response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers,
    )
    assert notify_response.status_code == 202

    call_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(
        line for line in call_response.text.splitlines() if line.startswith("data: ")
    )
    payload = json.loads(body_line.removeprefix("data: "))
    return payload["result"]


def test_read_only_tools_constant_matches_the_six_write_tools():
    assert READ_ONLY_TOOLS == {
        "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
        "create_bookmark",
    }


def test_save_app_config_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "save_app_config",
            {"itemId": "does-not-exist", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_create_item_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_item",
            {"kind": "app", "title": "X", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_create_form_app_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_form_app", {"collectionId": "does-not-exist"},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_create_dataset_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_dataset",
            {"title": "X", "source": "collection", "collectionId": "does-not-exist"},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_create_bookmark_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_bookmark",
            {"title": "X", "appId": "does-not-exist", "pageId": "page-1"},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_set_sharing_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "set_sharing",
            {"itemId": "does-not-exist", "sharing": {"public": False, "groups": []}},
        )
    assert READ_ONLY_MESSAGE in error_text


def test_read_only_mode_does_not_affect_read_tools(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        result = call_tool(app_client, "whoami", {})
    assert result["username"] == "mockuser"
