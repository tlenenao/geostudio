# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
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
    if not result["content"]:
        # Tools annotated `-> None` (e.g. set_sharing) surface as an empty
        # content list rather than a text block.
        return None
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


def test_get_sharing_defaults_to_private(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        result = call_tool(app_client, "get_sharing", {"itemId": item_id})

    assert result == {"public": False, "groups": []}


def test_set_sharing_then_get_sharing_round_trips(app_client):

    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    with app_client.session_factory() as session:
        session.add(
            Group(
                id="g1",
                tenant_id=app_client.tenant.id,
                name="G",
                created_by=app_client.mock_user.id,
            )
        )
        session.commit()

    with app_client:
        call_tool(
            app_client,
            "set_sharing",
            {
                "itemId": item_id,
                "sharing": {"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]},
            },
        )
        result = call_tool(app_client, "get_sharing", {"itemId": item_id})

    assert result == {"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]}


def test_get_sharing_invisible_to_a_stranger_errors(app_client):
    # Mirrors test_get_item_invisible_to_a_stranger_errors
    # (test_mcp_tools_items.py) — every existing test in this file calls
    # get_sharing/set_sharing on an item mock_user owns; the denial path was
    # never exercised for either tool.
    with app_client.session_factory() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="sub-stranger",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
        stranger_id = stranger.id
    item_id = _seed_item(app_client, owner_id=stranger_id, title="Not mine")

    with app_client:
        error_text = call_tool_expecting_error(app_client, "get_sharing", {"itemId": item_id})

    assert "not found" in error_text.lower()


def test_set_sharing_by_group_viewer_errors(app_client):
    # Mirrors test_save_app_config_by_group_viewer_errors
    # (test_mcp_tools_configs.py): mock_user can read the item (viewer share)
    # but has no editor/share role — set_sharing (action="share") must
    # refuse, not silently succeed.

    with app_client.session_factory() as session:
        owner = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="sub-owner",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        session.flush()
        item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=owner.id,
            resource_type="app",
            title="Shared",
        )
        group = Group(id="g1", tenant_id=app_client.tenant.id, name="G", created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(
            GroupMember(
                group_id=group.id, user_id=app_client.mock_user.id, tenant_id=app_client.tenant.id
            )
        )
        session.add(
            ItemShare(
                item_id=item.id, group_id=group.id, tenant_id=app_client.tenant.id, role="viewer"
            )
        )
        session.commit()
        item_id = item.id

    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "set_sharing",
            {"itemId": item_id, "sharing": {"public": True, "groups": []}},
        )

    assert "not allowed" in error_text.lower()


def test_set_sharing_with_unknown_group_errors(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "set_sharing",
            {
                "itemId": item_id,
                "sharing": {"public": False, "groups": [{"groupId": "nope", "role": "viewer"}]},
            },
        )

    assert "group" in error_text.lower()


def test_create_group_then_add_member_via_mcp(app_client):
    with app_client.session_factory() as session:
        bob = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="sub-bob",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
        bob_id = bob.id

    with app_client:
        created = call_tool(app_client, "create_group", {"name": "Équipe SIG"})
        assert created["name"] == "Équipe SIG"
        # list_groups (comme search_collections, Tâche 4) retourne une liste
        # nue — structuredContent["result"] est la forme fiable, pas
        # json.loads(content[0].text) (qui unwrap l'unique élément au lieu
        # d'un tableau JSON à un élément, vérifié empiriquement).
        raw_groups = call_tool_raw(app_client, "list_groups", {})
        groups = raw_groups["structuredContent"]["result"]
        assert any(g["id"] == created["id"] for g in groups)
        call_tool(app_client, "add_group_member", {"groupId": created["id"], "userId": bob_id})

    with app_client.session_factory() as session:
        from sqlalchemy import select

        member = session.scalar(
            select(GroupMember).where(
                GroupMember.group_id == created["id"], GroupMember.user_id == bob_id
            )
        )
        assert member is not None


def test_add_group_member_by_non_creator_raises(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="sub-owner2",
            username="owner2",
            email=None,
            first_name="",
            last_name="",
        )
        foreign_group = Group(
            id="foreign-g1",
            tenant_id=app_client.tenant.id,
            name="Foreign",
            created_by=other_owner.id,
        )
        session.add(foreign_group)
        session.commit()
        foreign_group_id = foreign_group.id

    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "add_group_member",
            {"groupId": foreign_group_id, "userId": app_client.mock_user.id},
        )

    assert "creator" in error_text.lower() or "not found" in error_text.lower()


def test_create_group_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(app_client, "create_group", {"name": "X"})
    assert "Mode démo : lecture seule, écritures désactivées." in error_text


def test_add_group_member_refuses_in_read_only_mode(app_client, monkeypatch):
    with app_client.session_factory() as session:
        group = Group(
            id="g-ro",
            tenant_id=app_client.tenant.id,
            name="G",
            created_by=app_client.mock_user.id,
        )
        session.add(group)
        session.commit()

    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "add_group_member",
            {"groupId": "g-ro", "userId": app_client.mock_user.id},
        )
    assert "Mode démo : lecture seule, écritures désactivées." in error_text


def test_set_sharing_writes_audit_log_with_agent_actor(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        call_tool(
            app_client,
            "set_sharing",
            {"itemId": item_id, "sharing": {"public": True, "groups": []}},
        )

    with app_client.session_factory() as session:
        from sqlalchemy import select

        from app.audit.models import AuditLog

        rows = session.scalars(select(AuditLog).where(AuditLog.action == "item.share")).all()
        assert len(rows) == 1
        assert rows[0].actor_kind == "agent"


def test_create_group_via_mcp_refuses_a_reader_with_no_privilege(app_client):
    # REV-009 : jumelle MCP de POST /groups. La garde catalog.manage posée
    # sur la route REST doit exister aussi ici, sinon create_group (MCP)
    # rouvre exactement le trou fermé côté REST (piège CLAUDE.md n°4).
    from app.roles.repository import ensure_built_in_roles
    from app.users.repository import set_user_role

    with app_client.session_factory() as session:
        roles = ensure_built_in_roles(session, tenant_id=app_client.tenant.id)
        assert roles["reader"].privileges == []
        set_user_role(
            session,
            tenant_id=app_client.tenant.id,
            user_id=app_client.mock_user.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        session.commit()

    with app_client:
        error_text = call_tool_expecting_error(app_client, "create_group", {"name": "Interdit"})

    assert "catalog.manage" in error_text
