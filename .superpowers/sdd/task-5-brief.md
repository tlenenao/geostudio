## Task 5: Core — `POST /copilot/turn` + wiring

**Files:**
- Create: `core/app/copilot/routes.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml` (import-linter layers)
- Create: `core/tests/test_copilot_routes.py`

**Interfaces:**
- Consumes: `get_llm_provider()`/`LLMTurn`/`ToolCall` (Task 3), `McpLoopbackSession`/`McpLoopbackError`/`ALLOWED_MCP_TOOL_NAMES` (Task 4), `get_current_user` (`app.auth.dependency`), `is_copilot_enabled` (Task 2).
- Produces: `router` (FastAPI `APIRouter`) in `app.copilot.routes`, mounted at `POST /copilot/turn` when `is_copilot_enabled()`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_copilot_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.copilot.llm_provider import FakeLLMProvider, LLMTurn, ToolCall
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_LLM_PROVIDER", "fake")
    monkeypatch.setenv("CORE_BASE_URL", "http://test")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app)
    test_client.headers["Authorization"] = "Bearer mock:alice"
    return test_client


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
            LLMTurn(text="", tool_calls=[ToolCall(id="1", name="whoami", arguments={})]),
            LLMTurn(text="Tu es connecté."),
        ]),
    )
    # whoami is not in ALLOWED_MCP_TOOL_NAMES: substitute a real allowlisted,
    # no-argument-friendly tool once verified in Task 4 (list_items with an
    # empty filter is a safe, side-effect-free choice) if `whoami` is
    # rejected as unallowlisted here — this test specifically wants a tool
    # the loopback actually executes, so use one from ALLOWED_MCP_TOOL_NAMES:
    resp = client.post("/copilot/turn", json={
        "itemId": "1", "message": "qui suis-je", "history": [],
        "mcpToken": "x", "currentConfig": {}, "clientTools": [],
    })
    assert resp.status_code == 200
    assert resp.json()["reply"] == "Désolé, je n'ai pas réussi à conclure cette demande — reformule ou simplifie." \
        or True  # placeholder replaced below once the real tool name is substituted


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
```

Fix `test_allowlisted_mcp_tool_call_is_executed_via_loopback` before running: replace `"whoami"` with `"list_items"` (a real allowlisted tool, per `ALLOWED_MCP_TOOL_NAMES` from Task 4) and its second scripted `LLMTurn` should be the final plain-text reply; assert `resp.json()["reply"] == "Tu es connecté."` and `resp.json()["clientOps"] == []` — this placeholder is intentionally left inconsistent above; correct it now to a real assertion:

```python
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
```

(Use this corrected version, not the placeholder shown first — the plan's "no placeholders" rule applies to the file you actually write, not this intermediate note.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.copilot.routes'`.

- [ ] **Step 3: Implement `routes.py`**

Create `core/app/copilot/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependency import get_current_user
from app.copilot.llm_provider import LLMTurn, get_llm_provider
from app.copilot.mcp_loopback import McpLoopbackError, McpLoopbackSession
from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES
from app.users.models import User

router = APIRouter()

MAX_TOOL_ITERATIONS = 6
TURN_TIMEOUT_SECONDS = 30.0


class CopilotMessage(BaseModel):
    role: str
    content: str


class CopilotTurnRequest(BaseModel):
    itemId: str
    message: str
    history: list[CopilotMessage] = []
    mcpToken: str
    currentConfig: dict
    clientTools: list[dict] = []


class ClientOp(BaseModel):
    op: str
    args: dict


class CopilotTurnResponse(BaseModel):
    reply: str
    clientOps: list[ClientOp]


def _system_message(item_id: str, current_config: dict) -> dict:
    return {
        "role": "system",
        "content": (
            "Tu es le copilote intégré au builder GeoStudio. Tu édites la "
            "configuration affichée par petites actions ciblées (widgets, "
            "sources de données), jamais en générant un tableau de bord "
            "entier d'un coup. Utilise les outils fournis ; ne réponds en "
            "texte libre que pour expliquer ou poser une question.\n\n"
            f"Item en cours d'édition : {item_id}\n"
            f"Configuration actuelle (JSON) : {current_config}"
        ),
    }


async def _run_turn(*, request: CopilotTurnRequest, mcp_session: McpLoopbackSession) -> CopilotTurnResponse:
    try:
        server_tools_raw = await mcp_session.list_tools()
    except McpLoopbackError as exc:
        raise HTTPException(status_code=502, detail=f"MCP loopback failed: {exc}") from exc
    server_tools = [t for t in server_tools_raw if t["name"] in ALLOWED_MCP_TOOL_NAMES]
    all_tools = server_tools + request.clientTools

    messages: list[dict] = [_system_message(request.itemId, request.currentConfig)]
    for m in request.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": request.message})

    provider = get_llm_provider()

    for _ in range(MAX_TOOL_ITERATIONS):
        turn: LLMTurn = provider.chat(messages, all_tools)
        if not turn.tool_calls:
            return CopilotTurnResponse(reply=turn.text, clientOps=[])

        client_ops: list[ClientOp] = []
        messages.append({
            "role": "assistant", "content": turn.text,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in turn.tool_calls
            ],
        })

        for tc in turn.tool_calls:
            if tc.name not in ALLOWED_MCP_TOOL_NAMES:
                # Ni dans l'allowlist MCP : soit un outil client déclaré par
                # le shell, soit un nom halluciné — dans les deux cas jamais
                # exécuté côté serveur. Une opération client ne produit
                # jamais de résultat réinjecté au LLM dans le même tour.
                client_ops.append(ClientOp(op=tc.name, args=tc.arguments))
                continue
            try:
                result = await mcp_session.call_tool(tc.name, tc.arguments)
            except McpLoopbackError as exc:
                raise HTTPException(status_code=502, detail=f"MCP loopback failed: {exc}") from exc
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": result.text or ("(erreur outil)" if result.is_error else ""),
            })

        if client_ops:
            return CopilotTurnResponse(reply=turn.text, clientOps=client_ops)

    return CopilotTurnResponse(
        reply="Désolé, je n'ai pas réussi à conclure cette demande — reformule ou simplifie.",
        clientOps=[],
    )


@router.post("/copilot/turn")
async def copilot_turn(
    body: CopilotTurnRequest,
    user: User = Depends(get_current_user),
) -> CopilotTurnResponse:
    mcp_session = McpLoopbackSession(body.mcpToken)
    try:
        return await asyncio.wait_for(
            _run_turn(request=body, mcp_session=mcp_session),
            timeout=TURN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Le copilote a mis trop de temps à répondre.") from exc
    finally:
        await mcp_session.aclose()
```

- [ ] **Step 4: Wire into `main.py`**

In `core/app/main.py`, update the import block (insert `app.copilot` alphabetically between `app.configs` and `app.dcat`):

Change:
```python
from app.configs import routes as configs_routes
from app.dcat import routes as dcat_routes
```
to:
```python
from app.configs import routes as configs_routes
from app.copilot import routes as copilot_routes
from app.dcat import routes as dcat_routes
```

Update the `app.auth.dependency` import (add `is_copilot_enabled`, alphabetically after `is_appexport_enabled`):

Change:
```python
from app.auth.dependency import (
    is_appexport_enabled, is_etl_enabled, is_export_enabled, is_read_only_mode,
    is_terrain3d_enabled, is_tileset3d_enabled,
)
```
to:
```python
from app.auth.dependency import (
    is_appexport_enabled, is_copilot_enabled, is_etl_enabled, is_export_enabled,
    is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)
```

Add `/copilot/turn` to the `read_only_guard` exemption list — even a read-only "explain this dataset" prompt is a POST, and MCP tools already self-gate writes internally (mirroring why `/mcp` itself is exempted here):

Change:
```python
    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and request.url.path != "/analytics/sql"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
            and not _EXPORT_PATH_RE.match(request.url.path)
        ):
```
to:
```python
    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and request.url.path != "/analytics/sql"
            and request.url.path != "/copilot/turn"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
            and not _EXPORT_PATH_RE.match(request.url.path)
        ):
```

Add the conditional router mount, after the `is_terrain3d_enabled()` block:

Change:
```python
    if is_terrain3d_enabled():
        app.include_router(terrain3d_routes.router)

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL")
```
to:
```python
    if is_terrain3d_enabled():
        app.include_router(terrain3d_routes.router)
    if is_copilot_enabled():
        app.include_router(copilot_routes.router)

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL")
```

- [ ] **Step 5: Import-linter contract**

In `core/pyproject.toml`, `app.copilot` needs nothing app-internal beyond `app.auth.dependency` and `app.users.models` (both near the bottom of the stack) and never imports `app.mcp` (it's a real HTTP loopback, invisible to import-linter). Insert it right after `"app.mcp",`:

Change:
```python
layers = [
    "app.main",
    "app.mcp",
    "app.public",
```
to:
```python
layers = [
    "app.main",
    "app.mcp",
    "app.copilot",
    "app.public",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_routes.py -v`
Expected: PASS (all 6, with the corrected `test_allowlisted_mcp_tool_call_is_executed_via_loopback`).

Then run the full backend suite and the import-linter check to make sure nothing else broke:

Run: `cd core && uv run pytest -q && uv run lint-imports`
Expected: all pass, `lint-imports` reports no contract violations.

- [ ] **Step 7: OpenAPI regen — verify empty diff**

Since the router is only mounted when `is_copilot_enabled()` is true (false by default, never set in CI), the generated OpenAPI spec should be unchanged — same precedent as `CORE_ETL_ENABLED`/pipelines.

Run:
```bash
cd core && uv run python scripts/export_openapi.py
git diff --stat core/openapi.json
```
Expected: no output from `git diff --stat` (empty diff). If it's NOT empty, do not silently accept it — investigate why the route leaked into the default-flags spec before proceeding, then run `cd shell && npm run gen:api-types` and commit the regenerated files too.

- [ ] **Step 8: Commit**

```bash
git add core/app/copilot/routes.py core/app/main.py core/pyproject.toml core/tests/test_copilot_routes.py
git commit -m "$(cat <<'EOF'
feat(core): POST /copilot/turn — boucle d'outils du copilote (SP-20)

Boucle jusqu'à 6 itérations : les tool_calls du LLM dans l'allowlist MCP
sont exécutés en loopback réel vers /mcp, tout le reste (outils client du
shell, ou un nom halluciné) est renvoyé tel quel comme clientOps sans
jamais s'exécuter côté serveur. Exempté du garde lecture-seule (comme
/mcp) — les outils MCP se gardent déjà eux-mêmes en écriture. Monté
seulement si CORE_LLM_PROVIDER est configuré.
EOF
)"
```

---

