# SPDX-License-Identifier: Apache-2.0
import pytest

from app import db
from app.attachments import repository as attachments_repo
from app.collections.models import Collection
from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES
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
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=mock_user.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()
        attachments_repo.create_attachment(
            setup_session,
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=3,
            s3_key=f"{tenant.id}/col1/f1/abc-a.jpg",
            created_by=mock_user.id,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    from fastapi.testclient import TestClient

    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


# Réutilise le patron call_tool/call_tool_raw de test_mcp_tools_items.py —
# copié ici pour ne pas créer une dépendance de test à test, comme les
# autres fichiers test_mcp_tools_*.py de ce dépôt (chacun est autonome).
def call_tool(test_client, name: str, arguments: dict) -> dict:
    import json

    result = call_tool_raw(test_client, name, arguments)
    if result.get("isError"):
        raise AssertionError(f"tool {name} errored: {result['content'][0]['text']}")
    return json.loads(result["content"][0]["text"])


def call_tool_expecting_error(test_client, name: str, arguments: dict) -> str:
    result = call_tool_raw(test_client, name, arguments)
    assert result.get("isError"), f"expected tool {name} to error, got: {result}"
    return result["content"][0]["text"]


def call_tool_raw(test_client, name: str, arguments: dict) -> dict:
    import json

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


def test_list_attachments_returns_metadata_without_a_file_url(app_client):
    # SP-42, correctif 2 (F-coeur-federation-08) : fileUrl pointait vers
    # GET /collections/{id}/items/{fid}/attachments/{aid}/file, gardée par
    # l'audience OIDC du shell (CORE_OIDC_AUDIENCE) — un jeton MCP porte
    # l'audience distincte CORE_MCP_AUDIENCE et reçoit systématiquement 401
    # sur cette route. Le tool ne doit donc plus produire ce champ.
    with app_client:
        result = call_tool(app_client, "list_attachments", {"collectionId": "col1", "fid": "f1"})
    assert len(result) == 1
    row = result[0]
    assert row["filename"] == "a.jpg"
    assert row["fieldKey"] == "photos"
    assert "fileUrl" not in row


def test_list_attachments_filters_by_field_key(app_client):
    with app_client:
        result = call_tool(
            app_client,
            "list_attachments",
            {"collectionId": "col1", "fid": "f1", "fieldKey": "documents"},
        )
    assert result == []


def test_list_attachments_errors_on_an_invisible_collection(app_client):
    with app_client.session_factory() as session:
        get_or_create_default_tenant(session)  # même tenant par défaut dans ce dépôt
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "list_attachments", {"collectionId": "does-not-exist", "fid": "f1"}
        )
    assert "not found" in error_text.lower()


def test_list_attachments_is_not_in_the_copilot_allowlist():
    assert "list_attachments" not in ALLOWED_MCP_TOOL_NAMES
