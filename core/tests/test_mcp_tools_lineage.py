# SPDX-License-Identifier: Apache-2.0
"""Tool MCP get_item_impact (ARC4-F15) : mêmes règles que la route REST."""

import json
import uuid

import pytest

from app import db
from app.collections.models import Collection
from app.configs.models import Config, ConfigRevision
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        s.add(
            Collection(
                id="col1",
                tenant_id=tenant.id,
                owner_id=user.id,
                table_name="col1",
                title="Col 1",
                pk_column="id",
            )
        )
        s.flush()
        item_id = uuid.uuid4().hex
        s.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                owner_id=user.id,
                resource_type="map",
                title="Carte",
            )
        )
        s.flush()
        cfg = uuid.uuid4().hex
        s.add(Config(id=cfg, tenant_id=tenant.id, kind="map", item_id=item_id, current_version=1))
        s.add(
            ConfigRevision(
                tenant_id=tenant.id,
                config_id=cfg,
                version=1,
                data={"kind": "map", "map": {"layers": [{"id": "l", "collectionId": "col1"}]}},
            )
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    from fastapi.testclient import TestClient

    client = TestClient(app, base_url="http://localhost:8200")
    client.map_id = item_id  # type: ignore[attr-defined]
    yield client
    engine.dispose()


# Réutilise le patron call_tool/call_tool_raw de test_mcp_tools_items.py —
# copié ici pour ne pas créer une dépendance de test à test, comme les
# autres fichiers test_mcp_tools_*.py de ce dépôt (chacun est autonome).
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


def test_get_item_impact_lists_dependents_of_a_collection(app_client):
    with app_client:
        result = call_tool(app_client, "get_item_impact", {"id": "col1", "type": "collection"})
    assert [d["title"] for d in result["dependents"]] == ["Carte"]
    assert result["hiddenCount"] == 0


def test_get_item_impact_unknown_target_is_an_error(app_client):
    with app_client:
        assert "not found" in call_tool_expecting_error(app_client, "get_item_impact", {"id": "x"})
