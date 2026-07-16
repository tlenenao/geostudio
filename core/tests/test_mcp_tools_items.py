# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.items import repository as items_repo
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    # create_app() builds its own engine from DATABASE_URL (app/main.py) and
    # the MCP tools close over *that* session_factory — not whatever engine
    # this fixture builds. A bare ":memory:" URL would give the fixture and
    # the app two disconnected databases (each ":memory:" SQLite connection
    # is its own private store), so the tools would never see data seeded
    # here. Route both through the same on-disk file instead.
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        # CORE_AUTH_MODE=mock always resolves this exact identity (see
        # app/auth/dependency.py's mock branch and MockTokenVerifier).
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
    """Drives one full MCP handshake (initialize -> notifications/initialized
    -> tools/call) and returns the parsed tool result. Raises AssertionError
    with the tool's error text if the call itself errored (is_error=True) —
    call helper for a SUCCESSFUL call; use call_tool_expecting_error below
    for tests that want to assert on failure."""
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


def _seed_item(test_client, *, owner_id, title="Item") -> str:
    with test_client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=test_client.tenant.id, owner_id=owner_id,
            resource_type="app", title=title,
        )
        session.commit()
        return item.id


def test_list_items_returns_owned_items(app_client):
    _seed_item(app_client, owner_id=app_client.mock_user.id, title="Mine")

    with app_client:
        result = call_tool(app_client, "list_items", {"scope": "mine"})

    assert result["total"] == 1
    assert result["items"][0]["title"] == "Mine"


def test_get_item_returns_owned_item(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id, title="Mine")

    with app_client:
        result = call_tool(app_client, "get_item", {"itemId": item_id})

    assert result["title"] == "Mine"
    assert result["owner"] == "mockuser"


def test_get_item_invisible_to_a_stranger_errors(app_client):
    with app_client.session_factory() as session:
        stranger = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="sub-stranger",
            username="stranger", email=None, first_name="", last_name="",
        )
        session.commit()
        stranger_id = stranger.id
    item_id = _seed_item(app_client, owner_id=stranger_id, title="Not mine")

    with app_client:
        error_text = call_tool_expecting_error(app_client, "get_item", {"itemId": item_id})

    assert "not found" in error_text.lower()


def test_get_item_visible_via_group_share_succeeds(app_client):
    with app_client.session_factory() as session:
        owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="sub-owner",
            username="owner", email=None, first_name="", last_name="",
        )
        session.flush()
        item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=owner.id,
            resource_type="app", title="Shared",
        )
        group = Group(id="g1", tenant_id=app_client.tenant.id, name="G", created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=app_client.mock_user.id, tenant_id=app_client.tenant.id))
        session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=app_client.tenant.id, role="viewer"))
        session.commit()
        item_id = item.id

    with app_client:
        result = call_tool(app_client, "get_item", {"itemId": item_id})

    assert result["title"] == "Shared"
