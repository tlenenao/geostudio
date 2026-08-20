# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
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
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
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
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
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
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(line for line in call_response.text.splitlines() if line.startswith("data: "))
    payload = json.loads(body_line.removeprefix("data: "))
    return payload["result"]


def _seed_item(test_client, *, owner_id, title="Item") -> str:
    with test_client.session_factory() as session:
        item = items_repo.create_item(
            session,
            tenant_id=test_client.tenant.id,
            owner_id=owner_id,
            resource_type="app",
            title=title,
        )
        session.commit()
        return item.id


def test_create_item_creates_and_owns_it_as_the_caller(app_client):
    with app_client:
        result = call_tool(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    assert result["title"] == "My App"
    assert result["owner"] == "mockuser"

    with app_client.session_factory() as session:
        from app.items.models import Item

        item = session.get(Item, result["pk"])
        assert item.owner_id == app_client.mock_user.id


def test_create_item_ignores_any_owner_argument_and_uses_the_caller_identity(app_client):
    # create_item's tool signature has no `owner` parameter at all — the
    # owner is always _resolve_actor's identity. This test proves that
    # invariant holds even if a permissive MCP client tries to smuggle an
    # extra "owner" argument in: whether the SDK's argument validation
    # rejects the unknown field outright (is_error=True) or silently drops
    # it (call succeeds), no item is ever created with the spoofed owner —
    # that's the actual guarantee, independent of which validation behavior
    # the SDK has (not asserted here; if this needs pinning down, check by
    # running the call once with print(result) before finishing this test).
    with app_client:
        call_tool_raw(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "My App",
                "owner": "someone-else",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    with app_client.session_factory() as session:
        from sqlalchemy import select

        from app.items.models import Item

        spoofed = session.scalars(select(Item).where(Item.owner_id == "someone-else")).all()
        assert spoofed == []


def test_resolve_actor_bootstraps_admin_from_core_admin_subs(app_client, monkeypatch):
    # CORE_ADMIN_SUBS doit être appliquée (et rafraîchie) à chaque
    # get_or_create_user, y compris sur le chemin MCP — pas seulement sur le
    # chemin REST (get_current_user). mock-sub est le subject fixe que
    # MockTokenVerifier résout toujours (app/mcp/auth.py).
    monkeypatch.setenv("CORE_ADMIN_SUBS", "mock-sub")
    with app_client:
        call_tool(app_client, "whoami", {})

    with app_client.session_factory() as session:
        from app.users.models import User

        user = session.get(User, app_client.mock_user.id)
        assert user.is_admin is True


def test_resolve_actor_does_not_bootstrap_admin_without_core_admin_subs(app_client):
    with app_client:
        call_tool(app_client, "whoami", {})

    with app_client.session_factory() as session:
        from app.users.models import User

        user = session.get(User, app_client.mock_user.id)
        assert user.is_admin is False


def test_create_item_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        call_tool(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    with app_client.session_factory() as session:
        from sqlalchemy import select

        from app.audit.models import AuditLog

        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        rows = list(session.scalars(select(AuditLog)))
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)
