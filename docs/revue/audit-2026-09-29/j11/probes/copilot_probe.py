"""Sonde du routeur copilote, exécutée DANS le conteneur cœur (le routeur n'est
pas monté tant que CORE_LLM_PROVIDER est vide). Monte seulement
app.copilot.routes.router sur une app FastAPI de test, avec un LLM et une session
MCP factices, puis imprime un JSON {cas: [statut, extrait]} sur stdout.
Lancée par shell/e2e/journeys/j11/copilot-server.spec.ts via `docker exec -i ... python -`."""

import json
import warnings

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependency import get_current_user
from app.copilot import routes as R
from app.copilot.llm_provider import LLMTurn, ToolCall

warnings.filterwarnings("ignore")


class U:
    oidc_sub = "s"


R.mcp_token_subject = lambda t: "s"
CALLS = []


class FakeSess:
    def __init__(self, *a, **k):
        pass

    async def list_tools(self):
        return [{"name": "search_catalog"}, {"name": "create_item"}, {"name": "save_app_config"}]

    async def call_tool(self, name, args):
        CALLS.append(name)

        class T:
            text = "{}"
            is_error = False

        return T()

    async def aclose(self):
        pass


R.McpLoopbackSession = FakeSess
app = FastAPI()
app.include_router(R.router)
app.dependency_overrides[get_current_user] = lambda: U()
client = TestClient(app, raise_server_exceptions=False)


def post(**kw):
    body = {
        "itemId": "i",
        "message": "hi",
        "history": [],
        "mcpToken": "t",
        "currentConfig": {},
        "clientTools": [],
    }
    body.update(kw)
    r = client.post("/copilot/turn", json=body)
    return [r.status_code, r.text[:200]]


class Boom:
    def __init__(self, exc):
        self.exc = exc

    async def chat(self, m, t):
        raise self.exc


class Scripted:
    def __init__(self, *turns):
        self.turns = list(turns)
        self.i = 0

    async def chat(self, m, t):
        turn = self.turns[min(self.i, len(self.turns) - 1)]
        self.i += 1
        return turn


req = httpx.Request("POST", "http://llm")
out = {}
for name, exc in [
    ("llm_http_429", httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))),
    ("llm_http_500", httpx.HTTPStatusError("500", request=req, response=httpx.Response(500, request=req))),
    ("llm_timeout", httpx.ReadTimeout("t", request=req)),
    ("llm_connect_error", httpx.ConnectError("x", request=req)),
    ("llm_bad_payload", KeyError("choices")),
]:
    R.get_llm_provider = lambda exc=exc: Boom(exc)
    out[name] = post()

R.get_llm_provider = lambda: Scripted(LLMTurn(text="ok"))
out["history_40"] = post(history=[{"role": "user", "content": "x"}] * 40)
out["history_41"] = post(history=[{"role": "user", "content": "x"}] * 41)
out["message_4001"] = post(message="x" * 4001)
out["history_message_8001"] = post(history=[{"role": "user", "content": "x" * 8001}])
out["config_64500"] = post(currentConfig={"a": "x" * 64500})
out["role_system_in_history"] = post(history=[{"role": "system", "content": "x"}])

CALLS.clear()
R.get_llm_provider = lambda: Scripted(
    LLMTurn(
        text="",
        tool_calls=[
            ToolCall(id="1", name="save_app_config", arguments={}),
            ToolCall(id="2", name="search_catalog", arguments={"q": "x"}),
        ],
    )
)
out["non_allowlisted_tool"] = post()
out["server_tools_called"] = CALLS[:]
print(json.dumps(out))
