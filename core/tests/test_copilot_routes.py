# SPDX-License-Identifier: Apache-2.0
import asyncio
import copy
import json
import time

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


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_copilot_app(monkeypatch):
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
    return app


@pytest.fixture()
def client(monkeypatch):
    app = _make_copilot_app(monkeypatch)
    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = "Bearer mock:alice"
        yield test_client


class CapturingLLMProvider:
    """Fake `LLMProvider` qui enregistre les `messages` reçus à chaque appel
    (copie profonde : `_run_turn` mute la même liste d'un tour à l'autre) —
    `FakeLLMProvider` ne les expose pas, et ce sont eux qui portent le
    contrat de forme OpenAI vérifié ici (C2/M6)."""

    def __init__(self, responses: list[LLMTurn], *, delay: float = 0.0):
        self._responses = responses
        self._i = 0
        self._delay = delay
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        self.calls.append(copy.deepcopy(messages))
        if self._delay:
            time.sleep(self._delay)
        turn = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return turn


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


def test_replayed_tool_call_arguments_are_a_json_string_not_a_dict(client, monkeypatch):
    """L'historique assistant réinjecté au tour suivant doit porter
    `function.arguments` en **chaîne** JSON : un vrai fournisseur OpenAI
    rejette un objet ("expected a string, but got an object")."""
    import app.copilot.routes as routes_module
    provider = CapturingLLMProvider([
        LLMTurn(text="", tool_calls=[ToolCall(id="1", name="list_items", arguments={"limit": 5})]),
        LLMTurn(text="Voici tes items."),
    ])
    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: provider)
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "liste mes items", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    assert len(provider.calls) == 2
    assistant = [m for m in provider.calls[1] if m.get("role") == "assistant"][-1]
    arguments = assistant["tool_calls"][0]["function"]["arguments"]
    assert isinstance(arguments, str)
    assert json.loads(arguments) == {"limit": 5}


def test_system_message_serialises_the_config_as_real_json(client, monkeypatch):
    """Le prompt annonce « (JSON) » : il doit vraiment en être — un
    `repr()` Python (guillemets simples, True/False/None) induirait le LLM
    en erreur sur les ids/valeurs qu'il doit réutiliser."""
    import app.copilot.routes as routes_module
    provider = CapturingLLMProvider([LLMTurn(text="ok")])
    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: provider)
    current_config = {
        "kind": "app", "published": True, "title": "Café & thé",
        "layout": {"items": [{"id": "w1", "type": "text", "hidden": None}]},
    }
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "explique", "history": [],
        "mcpToken": "x", "currentConfig": current_config, "clientTools": [],
    })
    assert resp.status_code == 200
    system = provider.calls[0][0]
    assert system["role"] == "system"
    marker = "Configuration actuelle (JSON) : "
    payload = system["content"].split(marker, 1)[1]
    assert json.loads(payload) == current_config
    assert "'kind': 'app'" not in system["content"]  # pas un repr() Python
    assert "Café & thé" in system["content"]  # ensure_ascii=False


@pytest.mark.anyio
async def test_synchronous_provider_call_does_not_block_the_event_loop(monkeypatch):
    """`provider.chat` est synchrone (httpx.post bloquant) : appelé
    directement dans la coroutine, il gèle tout le process pour la latence
    du LLM et neutralise le `asyncio.wait_for` du tour. Deux requêtes
    concurrentes ne doivent donc pas se sérialiser."""
    app = _make_copilot_app(monkeypatch)
    import app.copilot.routes as routes_module
    delay = 0.4
    monkeypatch.setattr(
        routes_module, "get_llm_provider",
        lambda: CapturingLLMProvider([LLMTurn(text="ok")], delay=delay),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200",
            headers={"Authorization": "Bearer mock:alice"},
        ) as http_client:
            body = {
                "itemId": "1", "message": "explique", "history": [],
                "mcpToken": "x", "currentConfig": {}, "clientTools": [],
            }
            # Requête d'échauffement : la base SQLite en mémoire est
            # partagée, et deux requêtes concurrentes se disputeraient la
            # création du tenant par défaut (artefact de test, sans rapport
            # avec ce qu'on mesure ici).
            warmup = await http_client.post("/copilot/turn", json=body)
            assert warmup.status_code == 200

            started = time.monotonic()
            responses = await asyncio.gather(
                http_client.post("/copilot/turn", json=body),
                http_client.post("/copilot/turn", json=body),
            )
            elapsed = time.monotonic() - started
    assert [r.status_code for r in responses] == [200, 200]
    assert elapsed < delay * 1.8, f"les deux tours se sont sérialisés ({elapsed:.2f}s pour 2×{delay}s)"
