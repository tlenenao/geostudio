# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    test_client = TestClient(app)
    yield test_client
    engine.dispose()


def test_mcp_endpoint_exists_and_requires_a_session(client):
    # A bare GET without the MCP protocol's required headers/session
    # negotiation won't succeed as a real tool call, but the route must
    # exist (not 404) — proves /mcp is actually mounted.
    response = client.get("/mcp")
    assert response.status_code != 404


def test_mcp_protected_resource_metadata_is_published(client):
    response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"].endswith("/mcp")
    assert len(body["authorization_servers"]) == 1


def test_mcp_whoami_tool_resolves_identity_through_the_full_lifespan(monkeypatch):
    # The other tests in this file never actually enter the app's lifespan
    # (TestClient only runs startup/shutdown when used as a context manager),
    # so a request never reaches session_manager.handle_request — auth
    # middleware rejects/accepts before that point either way. This test
    # uses `with TestClient(...) as client` specifically to prove the
    # combined lifespan really does start the MCP session manager (not
    # silently skip it), and that the whoami tool resolves through a full
    # initialize -> notifications/initialized -> tools/call handshake.
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    with TestClient(app, base_url="http://localhost:8200") as test_client:
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
                "params": {"name": "whoami", "arguments": {}},
            },
            headers=session_headers,
        )
        assert call_response.status_code == 200

        body_line = next(
            line for line in call_response.text.splitlines() if line.startswith("data: ")
        )
        payload = json.loads(body_line.removeprefix("data: "))
        result_text = payload["result"]["content"][0]["text"]
        whoami_result = json.loads(result_text)
        # MockTokenVerifier's fixed claims (Task 2) — same identity
        # get_current_user's mock branch would resolve for the shell's REST API.
        assert whoami_result["username"] == "mockuser"

    engine.dispose()


def test_mcp_rejects_request_without_authorization_header_in_oidc_mode(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app)

    response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "resource_metadata" in response.headers["WWW-Authenticate"]
    engine.dispose()
