## Task 4: Core — `mcp_loopback.py` + `tools_allowlist.py`

**Files:**
- Create: `core/app/copilot/mcp_loopback.py`
- Create: `core/app/copilot/tools_allowlist.py`
- Create: `core/tests/test_copilot_mcp_loopback.py`

**Interfaces:**
- Consumes: the app's own `/mcp` endpoint (mounted by `create_app()`, `core/app/main.py:236`), same JSON-RPC-over-HTTP handshake as `core/tests/test_mcp_routes.py` (`initialize` → `notifications/initialized` → `tools/list`/`tools/call`, SSE `data: ` line parsing).
- Produces: `McpLoopbackSession(mcp_token, http_client=None)` with `async list_tools() -> list[dict]`, `async call_tool(name, arguments) -> ToolCallResult`, `async aclose()`; `McpLoopbackError`; `ALLOWED_MCP_TOOL_NAMES: frozenset[str]`. Consumed by Task 5's `routes.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_copilot_mcp_loopback.py`, reusing the exact app-construction pattern from `core/tests/test_mcp_routes.py` (fresh `create_app()` + `sqlite` in-memory + `CORE_AUTH_MODE=mock`), but driving the loopback client through an ASGI-transport `httpx.AsyncClient` instead of the raw `TestClient`:

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app import db
from app.copilot.mcp_loopback import ALLOWED_MCP_TOOL_NAMES, McpLoopbackError, McpLoopbackSession
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://test")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    application = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    application.dependency_overrides[db.get_session] = override_session
    return application


@pytest.mark.asyncio
async def test_list_tools_returns_full_catalog(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            tools = await session.list_tools()
        finally:
            await session.aclose()
        names = {t["name"] for t in tools}
        assert ALLOWED_MCP_TOOL_NAMES <= names  # every allowlisted tool really exists server-side


@pytest.mark.asyncio
async def test_call_tool_returns_text_result(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            result = await session.call_tool("whoami", {})
        finally:
            await session.aclose()
        assert result.is_error is False
        assert "mockuser" in result.text


@pytest.mark.asyncio
async def test_call_tool_surfaces_tool_execution_error_without_raising(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            # get_item on a nonexistent id: the tool itself raises, MCP
            # reports it as a tool-level error (isError), not a protocol
            # failure — must not raise McpLoopbackError.
            result = await session.call_tool("get_item", {"itemId": "does-not-exist"})
        finally:
            await session.aclose()
        assert result.is_error is True


@pytest.mark.asyncio
async def test_call_tool_raises_on_unknown_tool_name(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            with pytest.raises(McpLoopbackError):
                await session.call_tool("not_a_real_tool", {})
        finally:
            await session.aclose()
```

Note: check `core/pyproject.toml`'s `[tool.pytest.ini_options]` for `asyncio_mode` — if it's not `"auto"`, add `@pytest.mark.asyncio` is already present above and confirm `pytest-asyncio` is a dependency (it must be, since `core/tests/test_mcp_routes.py`'s own async paths and the app's async route handlers are already tested elsewhere in this suite — if `uv run pytest` errors with "async def functions are not natively supported", check `core/pyproject.toml` for the marker registration and add `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` only if it's genuinely missing, matching whatever convention the rest of the suite already uses).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_mcp_loopback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.copilot.mcp_loopback'`.

- [ ] **Step 3: Implement**

Create `core/app/copilot/tools_allowlist.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Ensemble fermé des outils MCP que le copilote peut invoquer en loopback
(SP-20). Exclut délibérément save_app_config/set_sharing : le copilote
édite la config déjà ouverte dans le builder uniquement via des opérations
côté client (clientOps, jamais écrites en base pendant la conversation) ;
il peut CRÉER un nouvel item (create_item/create_form_app) via les mêmes
outils qu'un agent MCP externe, jamais muter un item existant directement."""

ALLOWED_MCP_TOOL_NAMES = frozenset({
    "search_catalog",
    "list_items",
    "explain_dataset",
    "run_analytics_query",
    "create_item",
    "create_form_app",
})
```

Create `core/app/copilot/mcp_loopback.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Client de rappel vers le serveur /mcp existant, pour la boucle
d'outils du copilote (SP-20) — un vrai appel réseau (HTTP), pas une
logique d'outil dupliquée. Réutilise le même protocole JSON-RPC-sur-HTTP
déjà exercé par core/tests/test_mcp_routes.py (initialize ->
notifications/initialized -> tools/list ou tools/call, réponse en SSE) :
un httpx.AsyncClient brut suffit, pas besoin du SDK client `mcp` (deuxième
dépendance client pour un seul appelant)."""
import json
import os
import uuid

import httpx


class McpLoopbackError(Exception):
    """Échec au niveau du protocole (poignée de main, HTTP, réponse
    malformée) — distinct d'un outil qui s'exécute et lève une erreur
    métier, renvoyée comme ToolCallResult(is_error=True) pour que le LLM
    la voie et puisse réagir, plutôt que de faire planter tout le tour."""


class ToolCallResult:
    def __init__(self, text: str, is_error: bool):
        self.text = text
        self.is_error = is_error


class McpLoopbackSession:
    """Une session par requête POST /copilot/turn — la poignée de main
    n'a lieu qu'une fois, paresseusement, au premier appel."""

    def __init__(self, mcp_token: str, *, http_client: httpx.AsyncClient | None = None):
        self._mcp_token = mcp_token
        self._client = http_client or httpx.AsyncClient(
            base_url=os.environ["CORE_BASE_URL"], timeout=15.0,
        )
        self._owns_client = http_client is None
        self._session_id: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._mcp_token}",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    async def _ensure_initialized(self) -> None:
        if self._session_id:
            return
        response = await self._client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "geostudio-copilot", "version": "0"},
                },
            },
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP initialize failed: {response.status_code}")
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise McpLoopbackError("MCP initialize did not return a session id")
        self._session_id = session_id
        notify = await self._client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers(),
        )
        if notify.status_code != 202:
            raise McpLoopbackError(f"MCP notifications/initialized failed: {notify.status_code}")

    def _parse_sse(self, response: httpx.Response) -> dict:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line.removeprefix("data: "))
        raise McpLoopbackError("no SSE data line in MCP response")

    async def list_tools(self) -> list[dict]:
        await self._ensure_initialized()
        response = await self._client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}},
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP tools/list failed: {response.status_code}")
        payload = self._parse_sse(response)
        if "error" in payload:
            raise McpLoopbackError(f"MCP tools/list error: {payload['error']}")
        return payload["result"]["tools"]

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        await self._ensure_initialized()
        response = await self._client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            headers=self._headers(),
        )
        if response.status_code == 401:
            raise McpLoopbackError("MCP token rejected (expired or wrong audience)")
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP tools/call failed: {response.status_code}")
        payload = self._parse_sse(response)
        if "error" in payload:
            # Erreur JSON-RPC de protocole (ex. nom d'outil inconnu) —
            # distincte d'un outil qui s'exécute et lève, cf. isError ci-dessous.
            raise McpLoopbackError(f"MCP tools/call error: {payload['error']}")
        result = payload["result"]
        content = result.get("content") or []
        text = content[0]["text"] if content else ""
        return ToolCallResult(text=text, is_error=bool(result.get("isError", False)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_mcp_loopback.py -v`
Expected: PASS (all 4). If `test_call_tool_surfaces_tool_execution_error_without_raising` fails because `get_item` isn't a real registered tool name, run `uv run pytest tests/test_copilot_mcp_loopback.py::test_list_tools_returns_full_catalog -v -s` and print `tools` to find any real registered tool that raises a `ValueError`-style "not found" on a bad id (check `core/app/mcp/tools.py` for one — `explain_dataset`/`run_analytics_query` on a bad `datasetId` are documented in SP-14o/SP-16b's own text as doing exactly this), and substitute that tool name/argument instead of `get_item`.

- [ ] **Step 5: Commit**

```bash
git add core/app/copilot/mcp_loopback.py core/app/copilot/tools_allowlist.py core/tests/test_copilot_mcp_loopback.py
git commit -m "$(cat <<'EOF'
feat(core): client de rappel MCP + allowlist d'outils pour le copilote (SP-20)

McpLoopbackSession parle JSON-RPC-sur-HTTP à /mcp, le même protocole déjà
exercé par test_mcp_routes.py — un vrai appel réseau, aucune logique
d'outil dupliquée. ALLOWED_MCP_TOOL_NAMES fixe les 6 outils accessibles au
copilote (jamais save_app_config/set_sharing).
EOF
)"
```

---

