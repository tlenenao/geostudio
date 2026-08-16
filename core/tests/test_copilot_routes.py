# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.copilot.llm_provider import FakeLLMProvider, LLMTurn, ToolCall
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app

# NOTE (deviation from the brief's Step 1, documented in task-5-report.md):
# routes.py's `copilot_turn` constructs `McpLoopbackSession(body.mcpToken)`
# with no injected `http_client`, so in production it makes a real network
# hop back to CORE_BASE_URL — that's the intended design (see
# mcp_loopback.py's module docstring). Naively setting CORE_BASE_URL to a
# fake host, as the brief's fixture originally did, makes every test that
# reaches _run_turn fail with httpx.ConnectError (DNS resolution), since
# there is nothing listening there. The fix, following the exact pattern
# already established by tests/test_copilot_mcp_loopback.py (Task 4): patch
# app.copilot.routes.McpLoopbackSession in the fixture to inject an
# httpx.AsyncClient wired via ASGITransport straight into this same `app`
# instance, so the loopback really executes the real /mcp handshake and
# tool dispatch in-process, and wrap TestClient as a context manager so the
# app's lifespan (which starts the MCP session manager) actually runs.


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_LLM_PROVIDER", "fake")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    import app.copilot.routes as routes_module
    real_mcp_loopback_session = routes_module.McpLoopbackSession

    def _loopback_session_via_asgi(mcp_token):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200",
        )
        return real_mcp_loopback_session(mcp_token, http_client=http_client)

    monkeypatch.setattr(routes_module, "McpLoopbackSession", _loopback_session_via_asgi)

    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = "Bearer mock:alice"
        yield test_client


def test_route_is_not_mounted_when_copilot_disabled(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    app = create_app()
    resp = TestClient(app).post("/copilot/turn", json={
        "itemId": "1", "message": "hi", "history": [], "mcpToken": "x",
        "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 404


def test_rejects_unauthenticated_request(client, monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")  # bypass the mock-mode auto-accept
    client.headers.pop("Authorization", None)
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "hi", "history": [], "mcpToken": "x",
        "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 401


def test_plain_text_reply_with_no_tool_calls(client, monkeypatch):
    import app.copilot.routes as routes_module
    monkeypatch.setattr(
        routes_module, "get_llm_provider",
        lambda: FakeLLMProvider(responses=[LLMTurn(text="Ce dataset contient des incidents.")]),
    )
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "explique ce dataset", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"reply": "Ce dataset contient des incidents.", "clientOps": []}


def test_unallowlisted_tool_call_is_returned_as_client_op_not_executed(client, monkeypatch):
    import app.copilot.routes as routes_module
    monkeypatch.setattr(
        routes_module, "get_llm_provider",
        lambda: FakeLLMProvider(responses=[
            LLMTurn(text="", tool_calls=[ToolCall(id="1", name="addWidget", arguments={"type": "text"})]),
        ]),
    )
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "ajoute un widget texte", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["clientOps"] == [{"op": "addWidget", "args": {"type": "text"}}]


def test_allowlisted_mcp_tool_call_is_executed_via_loopback(client, monkeypatch):
    import app.copilot.routes as routes_module
    monkeypatch.setattr(
        routes_module, "get_llm_provider",
        lambda: FakeLLMProvider(responses=[
            LLMTurn(text="", tool_calls=[ToolCall(id="1", name="list_items", arguments={})]),
            LLMTurn(text="Voici tes items."),
        ]),
    )
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "liste mes items", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Voici tes items.", "clientOps": []}


def test_hits_max_iterations_gracefully(client, monkeypatch):
    import app.copilot.routes as routes_module
    from app.copilot.routes import MAX_TOOL_ITERATIONS
    monkeypatch.setattr(
        routes_module, "get_llm_provider",
        lambda: FakeLLMProvider(responses=[
            LLMTurn(text="", tool_calls=[ToolCall(id=str(i), name="list_items", arguments={})])
            for i in range(MAX_TOOL_ITERATIONS + 2)
        ]),
    )
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "boucle", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    assert resp.json()["clientOps"] == []
    assert "n'ai pas réussi" in resp.json()["reply"]
