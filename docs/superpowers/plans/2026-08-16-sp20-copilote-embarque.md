# Copilote IA embarqué dans le builder (SP-20) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a chat panel to the app/dashboard builder that can explain data, search the catalogue, and propose micro-edits (add/update/remove a widget, add a data source, set a filter) on the config currently being edited — backed by a real loopback call to the existing `/mcp` server for read/search tools, never a second engine or a duplicated authorization path.

**Architecture:** `core/app/copilot/` exposes `POST /copilot/turn`, driving a pluggable `LLMProvider` in a tool-calling loop (max 6 iterations). MCP-allowlisted tool calls (`search_catalog`, `list_items`, `explain_dataset`, `run_analytics_query`, `create_item`, `create_form_app`) are executed via a real JSON-RPC-over-HTTP round trip to the app's own `/mcp` endpoint (same mechanism already proven in `core/tests/test_mcp_routes.py` — no `mcp` SDK client, no duplicated tool logic). Any other tool call the LLM makes is never executed server-side — it's returned as a `clientOps` entry. The shell's new `CopilotPanel` applies `clientOps` via `applyClientOp.ts`, reusing the exact pure functions (`grid.ts`/`pages.ts`) every other panel already funnels through, so every copilot edit lands in SP-19's single undo stack for free. The MCP-audience token the loopback call needs is obtained client-side via a second `signinSilent()` requesting Keycloak's pre-existing `geostudio-mcp-audience` optional client scope — a standard OIDC scope grant, not RFC 8693 token-exchange (see Task 1 for why).

**Tech Stack:** FastAPI + Pydantic (core), httpx (loopback + OpenAI-compatible LLM calls), React + react-oidc-context + TanStack Query (shell), Playwright (E2E), pytest + Vitest.

## Global Constraints

- Off by default: `copilotEnabled` (and the `/copilot/turn` router itself) is only active when `CORE_LLM_PROVIDER` is set — an instance that upgrades sees nothing new until an admin configures a provider (design §5).
- No new DB tables/models: this is stateless per-turn — the full message `history` round-trips from the client on every request (design §6: no persistent conversation history in v1).
- The copilot never mutates an item already open in the builder directly (no `save_app_config`/`set_sharing` in the MCP allowlist) — only client-side `clientOps` on the in-memory draft, applied through SP-19's undo stack, saved only via the existing "Enregistrer" button (design §3/§4).
- `updateWidgetProps`/`clientTools.ts` cover only **scalar** widget props (string/number/boolean/dataSource) via the new `configSchema` field — array/object-shaped props (`table.columns`, `drawer.items`, `tabs.tabs`, `form.fields`, `pivot.encodings`, `mapWidget.encodings`) are out of scope for v1 and simply absent from `configSchema`.
- Docs and commit messages in French; code/identifiers in English (CLAUDE.md).
- Conventional commits (`feat(core): …`, `feat(shell): …`), one subject each, small.
- TDD: write the failing test before the implementation, for every task that has one.
- Branch: `dev`.

---

## Task 1: Keycloak realm — MCP-audience scope on `geostudio-shell`

**Why this shape, not the design doc's original client-signinSilent-with-`resource`-param or a core-side token-exchange:** `deploy/keycloak/geostudio-realm.json` already defines a `geostudio-mcp-audience` client scope (custom-audience mapper, `consentRequired: false`) — provisioned in SP-2 for exactly this case, just never attached to `geostudio-shell`. Requesting it via the standard OIDC `scope` parameter on a second `signinSilent()` call is the established, version-independent mechanism (unlike RFC 8693 token-exchange, only available as a preview feature requiring fine-grained authorization config on Keycloak 24, the version pinned in `docker-compose.yml`).

**Files:**
- Modify: `deploy/keycloak/geostudio-realm.json` (the `geostudio-shell` client's `optionalClientScopes`)

- [ ] **Step 1: Add the scope**

In `deploy/keycloak/geostudio-realm.json`, find the `geostudio-shell` client object (`"clientId": "geostudio-shell"`) and change:

```json
      "optionalClientScopes": [
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt"
      ]
```

to:

```json
      "optionalClientScopes": [
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt",
        "geostudio-mcp-audience"
      ]
```

- [ ] **Step 2: Verify against a real Keycloak (docker compose)**

Run:

```bash
docker compose up -d keycloak
# Wait for it to report healthy:
docker compose ps keycloak
```

Once healthy (`docker compose ps keycloak` shows `healthy`), request a token via the Direct Access Grant (ROPC) flow — `geostudio-shell` is a public client with `directAccessGrantsEnabled: true`, and `alice`/`Demo1234!` is a seeded dev-only user in this same realm file (already public in this open-source repo, not a real credential):

```bash
curl -s -X POST http://localhost:8180/realms/geostudio/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=geostudio-shell \
  -d username=alice \
  -d password=Demo1234! \
  -d scope="openid geostudio-mcp-audience" \
  | python3 -c "
import json, sys, base64
tok = json.load(sys.stdin)['access_token']
payload = tok.split('.')[1]
payload += '=' * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print('aud:', claims['aud'])
assert 'geostudio-mcp' in claims['aud'], 'geostudio-mcp missing from aud!'
print('OK: geostudio-mcp present in aud')
"
```

Expected output: `aud: ['geostudio-core', 'geostudio-mcp']` (or similar, in some order) then `OK: geostudio-mcp present in aud`. If the realm didn't reload your edit (Keycloak only re-imports on a fresh volume), remove the `keycloak-data` volume first: `docker compose down keycloak && docker volume rm geostudio_keycloak-data && docker compose up -d keycloak` (check the exact volume name via `docker compose config --volumes` first — do not guess).

If this fails (audience missing), stop and re-investigate — do not proceed to Task 11 (`useMcpToken.ts`) on an unverified assumption.

- [ ] **Step 3: Commit**

```bash
git add deploy/keycloak/geostudio-realm.json
git commit -m "$(cat <<'EOF'
feat(deploy): geostudio-shell peut demander le scope d'audience MCP (SP-20)

Ajoute geostudio-mcp-audience aux optionalClientScopes de geostudio-shell —
scope déjà provisionné en SP-2, jusqu'ici jamais attaché à ce client.
Permet au shell d'obtenir un second token (audience geostudio-mcp) via
signinSilent({scope: "... geostudio-mcp-audience"}) sans passer par le
grant token-exchange (preview feature sur Keycloak 24).
EOF
)"
```

---

## Task 2: Core — `is_copilot_enabled()` + `GET /instance.copilotEnabled`

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/app/instance/routes.py`
- Create: `core/tests/test_copilot_enabled_flag.py`
- Modify: `core/tests/test_etl_enabled_flag.py`, `core/tests/test_export_enabled_flag.py`, `core/tests/test_read_only_mode.py` (their `GET /instance` exact-dict assertions gain a `copilotEnabled` key — see Step 4)

**Interfaces:**
- Produces: `is_copilot_enabled() -> bool` in `app.auth.dependency`, importable by `core/app/main.py` (Task 5).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_copilot_enabled_flag.py`, mirroring `core/tests/test_etl_enabled_flag.py` exactly:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_copilot_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_copilot_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    assert is_copilot_enabled() is False


def test_is_copilot_enabled_true_for_any_non_empty_provider(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "openai")
    assert is_copilot_enabled() is True
    monkeypatch.setenv("CORE_LLM_PROVIDER", "fake")
    assert is_copilot_enabled() is True


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_reports_copilot_disabled_by_default(env, monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["copilotEnabled"] is False


def test_instance_reports_copilot_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "openai")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["copilotEnabled"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_copilot_enabled'`.

- [ ] **Step 3: Implement**

In `core/app/auth/dependency.py`, add right after `is_terrain3d_enabled()` (before `admin_subs()`):

```python
def is_copilot_enabled() -> bool:
    """CORE_LLM_PROVIDER (SP-20) — contrairement aux autres capacités
    instance-wide ci-dessus (is_etl_enabled et consorts), ce n'est pas un
    booléen dédié : le copilote est actif dès qu'un fournisseur LLM est
    configuré, quelle que soit sa valeur (CORE_LLM_PROVIDER=openai, ou
    toute chaîne non vide). Lue à chaque appel, sans cache, même
    convention que is_read_only_mode ci-dessus."""
    return bool(os.environ.get("CORE_LLM_PROVIDER"))
```

In `core/app/instance/routes.py`, update the import and response dict:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import (
    is_appexport_enabled, is_copilot_enabled, is_etl_enabled, is_export_enabled,
    is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "appExportEnabled": is_appexport_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
        "terrain3dEnabled": is_terrain3d_enabled(),
        "copilotEnabled": is_copilot_enabled(),
    }
```

- [ ] **Step 4: Fix the three existing tests with brittle exact-dict assertions**

`GET /instance` is now a 7-key dict; three existing test files assert exact dict equality on the old 6-key shape and will break. Add `"copilotEnabled": False` to each:

In `core/tests/test_etl_enabled_flag.py`, both occurrences of:
```python
        "readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False,
    }
```
and
```python
        "readOnly": False, "etlEnabled": True, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False,
    }
```
become (append the key on its own trailing line before the closing brace):
```python
        "readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,
        "tileset3dEnabled": False, "terrain3dEnabled": False, "copilotEnabled": False,
    }
```
(and the `etlEnabled: True` variant keeps `copilotEnabled: False` — this file never sets `CORE_LLM_PROVIDER`).

In `core/tests/test_export_enabled_flag.py`, the one occurrence starting `"readOnly": False, "etlEnabled": False, "exportEnabled": False, "appExportEnabled": False,` gets the same `"copilotEnabled": False,` appended.

In `core/tests/test_read_only_mode.py`, both occurrences (`"readOnly": False, ...` and `"readOnly": True, ...`) get `"copilotEnabled": False,` appended the same way.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_enabled_flag.py tests/test_etl_enabled_flag.py tests/test_export_enabled_flag.py tests/test_read_only_mode.py tests/test_tileset3d_enabled_flag.py tests/test_terrain3d_enabled_flag.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py core/tests/test_copilot_enabled_flag.py core/tests/test_etl_enabled_flag.py core/tests/test_export_enabled_flag.py core/tests/test_read_only_mode.py
git commit -m "$(cat <<'EOF'
feat(core): capacité copilotEnabled sur GET /instance (SP-20)

is_copilot_enabled() reflète la présence de CORE_LLM_PROVIDER (pas un
booléen dédié, contrairement aux autres capacités) ; GET /instance
l'expose pour que le shell affiche ou non l'onglet copilote.
EOF
)"
```

---

## Task 3: Core — `llm_provider.py`

**Files:**
- Create: `core/app/copilot/__init__.py` (empty)
- Create: `core/app/copilot/llm_provider.py`
- Create: `core/tests/test_copilot_llm_provider.py`

**Interfaces:**
- Produces: `LLMProvider` (Protocol), `LLMTurn`, `ToolCall`, `FakeLLMProvider`, `OpenAICompatibleLLMProvider`, `get_llm_provider() -> LLMProvider`, all in `app.copilot.llm_provider`. Consumed by Task 5's `routes.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_copilot_llm_provider.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.copilot.llm_provider import (
    FakeLLMProvider, LLMTurn, ToolCall, get_llm_provider,
)


def test_fake_provider_returns_scripted_responses_in_order():
    provider = FakeLLMProvider(responses=[
        LLMTurn(text="", tool_calls=[ToolCall(id="1", name="search_catalog", arguments={"q": "x"})]),
        LLMTurn(text="Voici le résultat."),
    ])
    first = provider.chat(messages=[], tools=[])
    assert first.tool_calls[0].name == "search_catalog"
    second = provider.chat(messages=[], tools=[])
    assert second.text == "Voici le résultat."


def test_fake_provider_repeats_last_response_once_exhausted():
    provider = FakeLLMProvider(responses=[LLMTurn(text="unique")])
    provider.chat(messages=[], tools=[])
    again = provider.chat(messages=[], tools=[])
    assert again.text == "unique"


def test_get_llm_provider_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("CORE_LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


def test_get_llm_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValueError, match="unknown CORE_LLM_PROVIDER"):
        get_llm_provider()


def test_openai_compatible_provider_parses_tool_calls(monkeypatch):
    import httpx

    from app.copilot.llm_provider import OpenAICompatibleLLMProvider

    def fake_post(url, *, headers, json, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "function": {"name": "search_catalog", "arguments": '{"q": "incidents"}'},
                        }],
                    },
                }],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OpenAICompatibleLLMProvider(api_url="https://example/v1/chat", api_key="test-key", model="gpt-4o-mini")
    turn = provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert turn.tool_calls == [ToolCall(id="call_1", name="search_catalog", arguments={"q": "incidents"})]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_copilot_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.copilot'`.

- [ ] **Step 3: Implement**

Create `core/app/copilot/__init__.py` (empty file).

Create `core/app/copilot/llm_provider.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Fournisseur LLM enfichable pour le copilote (SP-20), même convention que
app.search.providers.EmbeddingProvider (SP-7) : un provider HTTP compatible
OpenAI pour la production, un provider déterministe sans réseau pour
dev/test/mock (CORE_LLM_PROVIDER=fake, ou absent)."""
import json
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn: ...


class FakeLLMProvider:
    """Réponses scriptées, consommées dans l'ordre ; la dernière est
    réutilisée si l'appelant en demande plus qu'il n'y en a — permet de
    scripter une boucle multi-tours (ex. un tool_call puis une réponse
    texte) sans dépendre du contenu réel des messages."""

    def __init__(self, responses: list[LLMTurn] | None = None):
        self._responses = responses or [LLMTurn(text="(réponse simulée)")]
        self._i = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        turn = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return turn


class OpenAICompatibleLLMProvider:
    def __init__(self, *, api_url: str, api_key: str, model: str):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        openai_tools = [{"type": "function", "function": t} for t in tools]
        response = httpx.post(
            self._api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": messages, "tools": openai_tools},
            timeout=30.0,
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"]["arguments"] or "{}"),
            )
            for tc in choice.get("tool_calls") or []
        ]
        return LLMTurn(text=choice.get("content") or "", tool_calls=tool_calls)


def get_llm_provider() -> LLMProvider:
    kind = os.environ.get("CORE_LLM_PROVIDER")
    if kind is None or kind == "fake":
        return FakeLLMProvider()
    if kind == "openai":
        return OpenAICompatibleLLMProvider(
            api_url=os.environ["CORE_LLM_API_URL"],
            api_key=os.environ["CORE_LLM_API_KEY"],
            model=os.environ.get("CORE_LLM_MODEL", "gpt-4o-mini"),
        )
    raise ValueError(f"unknown CORE_LLM_PROVIDER: {kind}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_copilot_llm_provider.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Commit**

```bash
git add core/app/copilot/__init__.py core/app/copilot/llm_provider.py core/tests/test_copilot_llm_provider.py
git commit -m "$(cat <<'EOF'
feat(core): fournisseur LLM enfichable pour le copilote (SP-20)

LLMProvider (Protocol) + FakeLLMProvider (scriptable, tests/mock) +
OpenAICompatibleLLMProvider (CORE_LLM_PROVIDER=openai), même patron que
app.search.providers.EmbeddingProvider (SP-7).
EOF
)"
```

---

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

## Task 6: Core — docker-compose.yml + .env.example wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Why this is its own task:** `CORE_EMBEDDING_PROVIDER` (SP-7) is documented in `.env.example` but was never wired into `docker-compose.yml`'s `core:` service — the packaged stack silently always runs embeddings in `fake` mode regardless of `.env`. This is the same bug class CLAUDE.md flags as recurring 3-4 times (SP-17a/17b/tileset3d/appexport): a capability that works when run directly but is dead in the packaged stack because compose only forwards env vars it explicitly lists. Do not repeat it here.

- [ ] **Step 1: docker-compose.yml**

In the `core:` service's `environment:` block, insert right after `CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}`:

Change:
```yaml
      CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
```
to:
```yaml
      CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
      CORE_LLM_PROVIDER: ${CORE_LLM_PROVIDER:-}
      CORE_LLM_API_URL: ${CORE_LLM_API_URL:-}
      CORE_LLM_API_KEY: ${CORE_LLM_API_KEY:-}
      CORE_LLM_MODEL: ${CORE_LLM_MODEL:-gpt-4o-mini}
```

- [ ] **Step 2: .env.example**

Insert a new section right after the existing MCP section (after `CORE_BASE_URL=http://localhost:8200` and its trailing blank line, before `# ─── Cœur : stockage des vignettes (MinIO / S3) ──────────`):

```
# ─── Cœur : copilote IA embarqué (SP-20) ─────────────────
# Vide (défaut) : le copilote est désactivé, le routeur POST /copilot/turn
# n'est pas monté, l'onglet n'apparaît pas dans le builder. "openai" active
# le fournisseur HTTP compatible OpenAI (chat completions + tool calling
# standard — vLLM/Ollama/LM Studio et la plupart des passerelles locales
# l'exposent aussi).
CORE_LLM_PROVIDER=
CORE_LLM_API_URL=
CORE_LLM_API_KEY=
CORE_LLM_MODEL=gpt-4o-mini

```

- [ ] **Step 3: Verify the compose file still parses**

Run: `docker compose config --quiet`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(deploy): variables du copilote IA dans la stack packagée (SP-20)

CORE_LLM_PROVIDER/API_URL/API_KEY/MODEL explicitement transmis au service
core — sans ça la capacité serait inactivable dans docker-compose.yml même
avec .env correctement renseigné (même classe de bug que CORE_EMBEDDING_*,
jamais câblé pour SP-7).
EOF
)"
```

---

## Task 7: Shell — `registry.ts` gains `configSchema`, backfill 22 builtin widgets

**Files:**
- Create: `shell/src/builder/widgetPropSchema.ts`
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/widgets/dateRangeFilter.tsx`, `datasetCard.tsx`, `chart.tsx`, `data.tsx` (list + table), `drawer.tsx`, `indicator.tsx`, `index.tsx` (text + image + button), `gallery.tsx`, `hero.tsx`, `richSection.tsx`, `filter.tsx`, `selectFilter.tsx`, `mapWidget.tsx`, `navigation.tsx`, `modal.tsx`, `tabs.tsx`, `sliderFilter.tsx`, `form.tsx`, `pivot.tsx`
- Create: `shell/src/builder/widgetPropSchema.test.ts`

**Interfaces:**
- Produces: `WidgetPropDescriptor` type (`shell/src/builder/widgetPropSchema.ts`), `WidgetDefinition.configSchema?: WidgetPropDescriptor[]` (`registry.ts`). Consumed by Task 9 (`clientTools.ts`) and Task 10 (`applyClientOp.ts`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/widgetPropSchema.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry, listWidgets } from "./registry";
import { registerBuiltinWidgets } from "./widgets";

describe("configSchema", () => {
  it("every builtin widget declares a configSchema (possibly empty)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    for (const w of listWidgets()) {
      expect(w.configSchema, `widget "${w.type}" has no configSchema`).toBeDefined();
    }
  });

  it("text widget's configSchema matches its scalar defaultProps", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const text = listWidgets().find((w) => w.type === "text");
    expect(text?.configSchema).toEqual([
      { name: "text", type: "string", label: "Texte", default: "Nouveau texte" },
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ]);
  });

  it("chart widget's configSchema covers all 15 scalar props", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const chart = listWidgets().find((w) => w.type === "chart");
    expect(chart?.configSchema).toHaveLength(15);
    expect(chart?.configSchema?.map((p) => p.name)).toContain("chartType");
  });

  it("tabs widget has an empty configSchema (its only prop, `tabs`, is array-shaped, out of scope for v1)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const tabs = listWidgets().find((w) => w.type === "tabs");
    expect(tabs?.configSchema).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts`
Expected: FAIL — `Cannot find module './widgetPropSchema'`.

- [ ] **Step 3: Create the shared type**

Create `shell/src/builder/widgetPropSchema.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Forme partagée par WidgetDefinition.configSchema (builtin widgets, ce
// fichier) et WcWidgetManifest.props (widgets WC/extension, SP-8,
// shell/src/builder/wc/manifest.ts) — même shape, délibérément non
// unifiées par un import commun pour ne pas toucher le module SP-8 : le
// typage structurel de TypeScript suffit à rendre les deux compatibles
// partout où clientTools.ts (Task 9) les consomme ensemble.
export type WidgetPropDescriptor = {
  name: string;
  type: "string" | "number" | "boolean" | "dataSource";
  label: string;
  default: unknown;
};
```

- [ ] **Step 4: Add `configSchema` to `WidgetDefinition`**

In `shell/src/builder/registry.ts`, add the import and the field:

Change:
```ts
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
```
to:
```ts
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
import type { WidgetPropDescriptor } from "./widgetPropSchema";
```

Change:
```ts
export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};
```
to:
```ts
export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  // Sous-ensemble des props éditables par le copilote (SP-20) — seules les
  // props scalaires (string/number/boolean/dataSource) ; les props
  // array/object (colonnes de table, items de tiroir, encodages...) restent
  // hors de portée, non listées ici.
  configSchema?: WidgetPropDescriptor[];
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};
```

- [ ] **Step 5: Backfill each widget**

`shell/src/builder/widgets/dateRangeFilter.tsx`:
```ts
    defaultProps: { label: "Période" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { label: "Période" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [{ name: "label", type: "string", label: "Libellé", default: "Période" }],
```

`shell/src/builder/widgets/datasetCard.tsx`:
```ts
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "showDownload", type: "boolean", label: "Afficher le téléchargement", default: true },
      { name: "title", type: "string", label: "Titre", default: "" },
    ],
```

`shell/src/builder/widgets/chart.tsx`:
```ts
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous",
    },
```
Insert right after that closing `},` of `defaultProps` (before `defaultSize`):
```ts
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "chartType", type: "string", label: "Type de graphique", default: "bar" },
      { name: "categoryField", type: "string", label: "Champ catégorie", default: "" },
      { name: "valueField", type: "string", label: "Champ valeur", default: "" },
      { name: "stack", type: "boolean", label: "Empilé", default: false },
      { name: "legend", type: "boolean", label: "Légende", default: true },
      { name: "zoom", type: "boolean", label: "Zoom", default: false },
      { name: "xAxisType", type: "string", label: "Type d'axe X", default: "category" },
      { name: "yAxisType", type: "string", label: "Type d'axe Y", default: "value" },
      { name: "yAxisFormat", type: "string", label: "Format axe Y", default: "" },
      { name: "yAxisUnit", type: "string", label: "Unité axe Y", default: "" },
      { name: "title", type: "string", label: "Titre", default: "" },
      { name: "advancedOption", type: "string", label: "Option ECharts avancée (JSON)", default: "" },
      { name: "compareEnabled", type: "boolean", label: "Comparaison de période", default: false },
      { name: "comparePeriod", type: "string", label: "Période de comparaison", default: "previous" },
    ],
```

`shell/src/builder/widgets/data.tsx` — two widgets in this file. For `type: "list"`:
```ts
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "titleField", type: "string", label: "Champ titre", default: "" },
    ],
```
For `type: "table"`:
```ts
    defaultProps: { dataSourceId: "", columns: [], pageSize: 10 },
    defaultSize: { w: 6, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", columns: [], pageSize: 10 },
    defaultSize: { w: 6, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "pageSize", type: "number", label: "Lignes par page", default: 10 },
    ],
```

`shell/src/builder/widgets/drawer.tsx`:
```ts
    defaultProps: { title: "Tiroir", items: [], side: "right" },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { title: "Tiroir", items: [], side: "right" },
    defaultSize: { w: 3, h: 1 },
    configSchema: [
      { name: "title", type: "string", label: "Titre", default: "Tiroir" },
      { name: "side", type: "string", label: "Côté", default: "right" },
    ],
```

`shell/src/builder/widgets/indicator.tsx`:
```ts
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
```
→
```ts
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Indicateur" },
      { name: "agg", type: "string", label: "Agrégation", default: "count" },
      { name: "field", type: "string", label: "Champ", default: "" },
    ],
```

`shell/src/builder/widgets/index.tsx` — three widgets. For `type: "text"`:
```ts
    defaultProps: { text: "Nouveau texte", dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
```
→
```ts
    defaultProps: { text: "Nouveau texte", dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
    configSchema: [
      { name: "text", type: "string", label: "Texte", default: "Nouveau texte" },
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ],
```
For `type: "image"`:
```ts
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
```
→
```ts
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "src", type: "string", label: "URL", default: "" },
      { name: "alt", type: "string", label: "Texte alternatif", default: "" },
    ],
```
For `type: "button"`:
```ts
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
```
→
```ts
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    configSchema: [
      { name: "label", type: "string", label: "Libellé", default: "Bouton" },
      { name: "href", type: "string", label: "Lien", default: "" },
    ],
```

`shell/src/builder/widgets/gallery.tsx`:
```ts
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
```
→
```ts
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
    configSchema: [
      { name: "type", type: "string", label: "Type d'item", default: "" },
      { name: "tag", type: "string", label: "Tag", default: "" },
      { name: "limit", type: "number", label: "Nombre max", default: 12 },
      { name: "columns", type: "number", label: "Colonnes", default: 3 },
    ],
```

`shell/src/builder/widgets/hero.tsx`:
```ts
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
```
→
```ts
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
    configSchema: [
      { name: "title", type: "string", label: "Titre", default: "Titre" },
      { name: "subtitle", type: "string", label: "Sous-titre", default: "" },
      { name: "backgroundImageUrl", type: "string", label: "Image de fond (URL)", default: "" },
      { name: "ctaLabel", type: "string", label: "Libellé du bouton", default: "" },
      { name: "ctaHref", type: "string", label: "Lien du bouton", default: "" },
      { name: "align", type: "string", label: "Alignement", default: "left" },
    ],
```

`shell/src/builder/widgets/richSection.tsx`:
```ts
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
```
→
```ts
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
    configSchema: [{ name: "markdown", type: "string", label: "Markdown", default: "" }],
```

`shell/src/builder/widgets/filter.tsx`:
```ts
    defaultProps: { field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 1 },
    configSchema: [
      { name: "field", type: "string", label: "Champ à filtrer", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/selectFilter.tsx`:
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
```
→
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "field", type: "string", label: "Champ", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/mapWidget.tsx`:
```ts
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
```
→
```ts
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    configSchema: [{ name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" }],
```

`shell/src/builder/widgets/navigation.tsx`:
```ts
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [{ name: "direction", type: "string", label: "Direction", default: "horizontal" }],
```

`shell/src/builder/widgets/modal.tsx`:
```ts
    defaultProps: { title: "Modale", items: [] },
    defaultSize: { w: 3, h: 1 },
```
→
```ts
    defaultProps: { title: "Modale", items: [] },
    defaultSize: { w: 3, h: 1 },
    configSchema: [{ name: "title", type: "string", label: "Titre", default: "Modale" }],
```

`shell/src/builder/widgets/tabs.tsx`:
```ts
    defaultProps: { tabs: [{ id: "tab-1", label: "Onglet 1", items: [] }] },
    defaultSize: { w: 6, h: 6 },
```
→
```ts
    defaultProps: { tabs: [{ id: "tab-1", label: "Onglet 1", items: [] }] },
    defaultSize: { w: 6, h: 6 },
    // Son seul champ, `tabs`, est array-shaped — hors de portée pour
    // updateWidgetProps en v1 (cf. Global Constraints). Rien à lister ici.
    configSchema: [],
```

`shell/src/builder/widgets/sliderFilter.tsx`:
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
```
→
```ts
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "field", type: "string", label: "Champ", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
```

`shell/src/builder/widgets/form.tsx`:
```ts
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
```
→
```ts
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
    // `fields` est array-shaped (hors de portée) ; `geometryType` est un
    // enum nullable qui ne rentre pas dans les 4 types de
    // WidgetPropDescriptor — laissé de côté plutôt que forcé.
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "submitLabel", type: "string", label: "Libellé du bouton", default: "Enregistrer" },
    ],
```

`shell/src/builder/widgets/pivot.tsx`:
```ts
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
```
→
```ts
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "title", type: "string", label: "Titre", default: "" },
    ],
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts src/builder/registry.test.tsx`
Expected: PASS.

- [ ] **Step 7: Run the full shell type-check + test suite**

Run: `cd shell && npm run build && npm run test`
Expected: PASS (tsc --noEmit + vite build succeed, all 22 widget files still register correctly, no other test broke).

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgetPropSchema.ts shell/src/builder/registry.ts shell/src/builder/widgets/ shell/src/builder/widgetPropSchema.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): configSchema sur WidgetDefinition, backfill des 22 widgets (SP-20)

Chaque widget builtin déclare désormais la liste de ses props scalaires
éditables (string/number/boolean/dataSource) — les props array/object
(columns, items, fields, encodings, tabs) restent hors schéma, hors
périmètre v1 du copilote. Base pour clientTools.ts (génération des outils
"client" depuis le registre, Task 9).
EOF
)"
```

---

## Task 8: Shell — `clientTools.ts`

**Files:**
- Create: `shell/src/builder/copilot/clientTools.ts`
- Create: `shell/src/builder/copilot/clientTools.test.ts`

**Interfaces:**
- Consumes: `listWidgets()` (`../registry`), `WidgetPropDescriptor` (`../widgetPropSchema`).
- Produces: `buildClientToolSchemas(): Array<{ name: string; description: string; inputSchema: Record<string, unknown> }>`. Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/copilot/clientTools.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { buildClientToolSchemas } from "./clientTools";

describe("buildClientToolSchemas", () => {
  it("returns exactly the 5 client tools by name", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const names = buildClientToolSchemas().map((t) => t.name);
    expect(names).toEqual(["addWidget", "updateWidgetProps", "removeWidget", "addDataSource", "setFilter"]);
  });

  it("addWidget's enum lists every registered widget type", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const addWidget = buildClientToolSchemas().find((t) => t.name === "addWidget")!;
    const enumValues = (addWidget.inputSchema as { properties: { type: { enum: string[] } } }).properties.type.enum;
    expect(enumValues).toContain("text");
    expect(enumValues).toContain("chart");
    expect(enumValues).toHaveLength(22);
  });

  it("updateWidgetProps' schema includes chart's scalar fields", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const updateProps = buildClientToolSchemas().find((t) => t.name === "updateWidgetProps")!;
    const props = (updateProps.inputSchema as { properties: { props: { properties: Record<string, unknown> } } })
      .properties.props.properties;
    expect(props).toHaveProperty("chartType");
    expect(props).toHaveProperty("dataSourceId");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/copilot/clientTools.test.ts`
Expected: FAIL — `Cannot find module './clientTools'`.

- [ ] **Step 3: Implement**

Create `shell/src/builder/copilot/clientTools.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Schémas d'outils "client" pour le copilote (SP-20) — générés depuis le
// registre de widgets plutôt que maintenus à la main : un nouveau widget
// (builtin ou WC/extension — configSchema et WcWidgetManifest.props ont la
// même forme, cf. widgetPropSchema.ts) devient automatiquement éditable
// sans code copilote supplémentaire. Reconstruits à chaque tour (jamais mis
// en cache) pour capter les extensions chargées dynamiquement après le
// montage du builder (useActiveExtensions).
import { listWidgets } from "../registry";
import type { WidgetPropDescriptor } from "../widgetPropSchema";

type ClientToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };

function jsonSchemaForProp(p: WidgetPropDescriptor): Record<string, unknown> {
  if (p.type === "boolean") return { type: "boolean", description: p.label };
  if (p.type === "number") return { type: "number", description: p.label };
  return { type: "string", description: p.label }; // "string" | "dataSource"
}

export function buildClientToolSchemas(): ClientToolSchema[] {
  const widgets = listWidgets();
  const widgetTypes = widgets.map((w) => w.type);

  const updateProperties: Record<string, unknown> = {};
  for (const w of widgets) {
    for (const p of w.configSchema ?? []) {
      updateProperties[p.name] = jsonSchemaForProp(p);
    }
  }

  return [
    {
      name: "addWidget",
      description: "Ajoute un widget sur la page en cours d'édition, avec ses props par défaut.",
      inputSchema: {
        type: "object",
        properties: { type: { type: "string", enum: widgetTypes, description: "Type de widget à ajouter" } },
        required: ["type"],
      },
    },
    {
      name: "updateWidgetProps",
      description: "Modifie les props d'un widget déjà présent sur le canevas, identifié par son id.",
      inputSchema: {
        type: "object",
        properties: {
          widgetId: { type: "string", description: "Identifiant du widget (item.id)" },
          props: { type: "object", description: "Propriétés à fusionner sur le widget", properties: updateProperties },
        },
        required: ["widgetId", "props"],
      },
    },
    {
      name: "removeWidget",
      description: "Retire un widget de la page en cours d'édition.",
      inputSchema: {
        type: "object",
        properties: { widgetId: { type: "string", description: "Identifiant du widget (item.id)" } },
        required: ["widgetId"],
      },
    },
    {
      name: "addDataSource",
      description: "Ajoute une source de données à la config.",
      inputSchema: {
        type: "object",
        properties: {
          id: { type: "string" },
          type: { type: "string", enum: ["features", "static", "statistics"] },
          service: { type: "string" },
          layer: { type: "string", description: "Identifiant de la collection ou du dataset" },
        },
        required: ["id", "type", "service", "layer"],
      },
    },
    {
      name: "setFilter",
      description: "Modifie la requête (filtre) d'une source de données existante.",
      inputSchema: {
        type: "object",
        properties: {
          dataSourceId: { type: "string" },
          query: { type: "object", description: "Objet de requête/filtre appliqué à la source" },
        },
        required: ["dataSourceId", "query"],
      },
    },
  ];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/copilot/clientTools.test.ts`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/copilot/clientTools.ts shell/src/builder/copilot/clientTools.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): clientTools.ts — schémas d'outils client générés du registre (SP-20)

buildClientToolSchemas() dérive addWidget/updateWidgetProps/removeWidget/
addDataSource/setFilter depuis registry.ts (configSchema) — un widget
enregistré devient éditable par le copilote sans code dédié.
EOF
)"
```

---

## Task 9: Shell — `applyClientOp.ts`

**Files:**
- Create: `shell/src/builder/copilot/applyClientOp.ts`
- Create: `shell/src/builder/copilot/applyClientOp.test.ts`

**Interfaces:**
- Consumes: `getWidget` (`../registry`), `getPageLayout`/`setPageLayout` (`../pages`), `nextFreePosition` (`../grid`), `AppConfig`/`DataSource`/`WidgetItem` (`../../api/types`).
- Produces: `RawClientOp` type, `applyClientOp(raw: RawClientOp, config: AppConfig, activePageId: string): AppConfig` (pure). Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/copilot/applyClientOp.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach } from "vitest";
import type { AppConfig } from "../../api/types";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { applyClientOp } from "./applyClientOp";

function emptyConfig(): AppConfig {
  return {
    kind: "app", theme: {} as AppConfig["theme"], dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

describe("applyClientOp", () => {
  beforeEach(() => {
    _resetRegistry();
    registerBuiltinWidgets();
  });

  it("addWidget adds an item with the widget's default props/size", () => {
    const config = applyClientOp({ op: "addWidget", args: { type: "text" } }, emptyConfig(), "page-1");
    expect(config.layout.items).toHaveLength(1);
    expect(config.layout.items[0].widget).toBe("text");
    expect(config.layout.items[0].props).toEqual({ text: "Nouveau texte", dataSourceId: "" });
  });

  it("addWidget with an unknown type is a no-op", () => {
    const config = applyClientOp({ op: "addWidget", args: { type: "not-a-real-widget" } }, emptyConfig(), "page-1");
    expect(config.layout.items).toHaveLength(0);
  });

  it("updateWidgetProps merges only keys present in configSchema, coerced by type", () => {
    let config = applyClientOp({ op: "addWidget", args: { type: "indicator" } }, emptyConfig(), "page-1");
    const widgetId = config.layout.items[0].id;
    config = applyClientOp(
      { op: "updateWidgetProps", args: { widgetId, props: { label: "Incidents ouverts", agg: 42, notARealProp: "x" } } },
      config, "page-1",
    );
    expect(config.layout.items[0].props).toEqual({
      dataSourceId: "", label: "Incidents ouverts", agg: "42", field: "",
    });
  });

  it("removeWidget removes the item by id", () => {
    let config = applyClientOp({ op: "addWidget", args: { type: "text" } }, emptyConfig(), "page-1");
    const widgetId = config.layout.items[0].id;
    config = applyClientOp({ op: "removeWidget", args: { widgetId } }, config, "page-1");
    expect(config.layout.items).toHaveLength(0);
  });

  it("addDataSource appends a new source, ignoring a duplicate id", () => {
    let config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" } },
      emptyConfig(), "page-1",
    );
    expect(config.dataSources).toEqual([{ id: "ds1", type: "features", service: "ogc", layer: "incidents", query: {} }]);
    config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "other" } },
      config, "page-1",
    );
    expect(config.dataSources).toHaveLength(1); // duplicate id ignored
  });

  it("setFilter updates an existing source's query", () => {
    let config = applyClientOp(
      { op: "addDataSource", args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" } },
      emptyConfig(), "page-1",
    );
    config = applyClientOp(
      { op: "setFilter", args: { dataSourceId: "ds1", query: { status: "open" } } },
      config, "page-1",
    );
    expect(config.dataSources[0].query).toEqual({ status: "open" });
  });

  it("an unknown op name is a no-op, never throws", () => {
    const config = emptyConfig();
    const result = applyClientOp({ op: "deleteEverything", args: {} }, config, "page-1");
    expect(result).toBe(config);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: FAIL — `Cannot find module './applyClientOp'`.

- [ ] **Step 3: Implement**

Create `shell/src/builder/copilot/applyClientOp.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Exécute une opération "client" proposée par le copilote (SP-20) en
// réutilisant les mêmes fonctions pures que la palette/PropsPanel
// (grid.ts/pages.ts) — toute opération traverse donc le même chemin que
// l'UI manuelle. Pure : le résultat passe par setDraft (undo SP-19) côté
// appelant (CopilotPanel), jamais ici.
import type { AppConfig, DataSource, WidgetItem } from "../../api/types";
import { nextFreePosition } from "../grid";
import { getPageLayout, setPageLayout } from "../pages";
import { getWidget } from "../registry";

// Forme brute reçue du cœur (Pydantic ClientOp côté serveur, JSON opaque) —
// peut être n'importe quel nom d'outil que le LLM a proposé, y compris un
// nom halluciné qui ne correspond à aucun des 5 op ci-dessous : voir le
// `default` du switch plus bas.
export type RawClientOp = { op: string; args: Record<string, unknown> };

function coerceProp(value: unknown, type: "string" | "number" | "boolean" | "dataSource"): unknown {
  if (type === "number") return Number(value);
  if (type === "boolean") return Boolean(value);
  return String(value ?? ""); // "string" | "dataSource"
}

export function applyClientOp(raw: RawClientOp, config: AppConfig, activePageId: string): AppConfig {
  const layout = getPageLayout(config, activePageId);

  switch (raw.op) {
    case "addWidget": {
      const type = String(raw.args.type ?? "");
      const def = getWidget(type);
      if (!def) return config;
      const { x, y } = nextFreePosition(layout.items);
      const item: WidgetItem = {
        id: crypto.randomUUID(), widget: type, x, y,
        w: def.defaultSize.w, h: def.defaultSize.h, props: { ...def.defaultProps },
      };
      return setPageLayout(config, activePageId, { ...layout, items: [...layout.items, item] });
    }
    case "updateWidgetProps": {
      const widgetId = String(raw.args.widgetId ?? "");
      const patch = (raw.args.props ?? {}) as Record<string, unknown>;
      const item = layout.items.find((i) => i.id === widgetId);
      if (!item) return config;
      const schema = getWidget(item.widget)?.configSchema ?? [];
      const allowed = new Map(schema.map((p) => [p.name, p.type]));
      const safePatch: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(patch)) {
        const type = allowed.get(key);
        if (!type) continue; // clé hors configSchema : jamais fusionnée telle quelle
        safePatch[key] = coerceProp(value, type);
      }
      return setPageLayout(config, activePageId, {
        ...layout,
        items: layout.items.map((i) => (i.id === widgetId ? { ...i, props: { ...i.props, ...safePatch } } : i)),
      });
    }
    case "removeWidget": {
      const widgetId = String(raw.args.widgetId ?? "");
      return setPageLayout(config, activePageId, {
        ...layout, items: layout.items.filter((i) => i.id !== widgetId),
      });
    }
    case "addDataSource": {
      const { id, type, service, layer } = raw.args as { id: string; type: DataSource["type"]; service: string; layer: string };
      if (!id || config.dataSources.some((s) => s.id === id)) return config;
      const source: DataSource = { id, type, service, layer, query: {} };
      return { ...config, dataSources: [...config.dataSources, source] };
    }
    case "setFilter": {
      const dataSourceId = String(raw.args.dataSourceId ?? "");
      const query = (raw.args.query ?? {}) as Record<string, unknown>;
      return {
        ...config,
        dataSources: config.dataSources.map((s) => (s.id === dataSourceId ? { ...s, query } : s)),
      };
    }
    default:
      return config;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/copilot/applyClientOp.ts shell/src/builder/copilot/applyClientOp.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): applyClientOp.ts — exécute les opérations du copilote (SP-20)

Pure, réutilise nextFreePosition/getPageLayout/setPageLayout — même
chemin que la palette/PropsPanel. updateWidgetProps filtre et coerce par
configSchema (jamais un merge opaque) ; un op au nom inconnu est un no-op.
EOF
)"
```

---

## Task 10: Shell — `useMcpToken.ts`

**Files:**
- Modify: `shell/src/auth/useAuth.ts` (export `isMockMode()`)
- Create: `shell/src/builder/copilot/useMcpToken.ts`
- Create: `shell/src/builder/copilot/useMcpToken.test.tsx`

**Interfaces:**
- Consumes: `useAuth as useOidcAuth` from `react-oidc-context`, `isMockMode` from `../../auth/useAuth`.
- Produces: `useMcpToken(): () => Promise<string>`. Consumed by Task 13 (`CopilotPanel.tsx`).

- [ ] **Step 1: Add `isMockMode()` to `useAuth.ts`**

In `shell/src/auth/useAuth.ts`, add right after `enableMockAuth`:

Change:
```ts
let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}
```
to:
```ts
let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}
export function isMockMode(): boolean {
  return mockMode;
}
```

- [ ] **Step 2: Write the failing tests**

Create `shell/src/builder/copilot/useMcpToken.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    signinSilent: vi.fn().mockResolvedValue({ access_token: "real-mcp-token" }),
  }),
}));

describe("useMcpToken", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("returns a fixed mock token synchronously in mock mode", async () => {
    enableMockAuth();
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const token = await result.current();
    expect(token).toBe("mock-mcp-token");
  });
});
```

Note: since `enableMockAuth()` sets a module-level flag with no reset function, this test file must run in isolation from `useMcpToken`'s non-mock behavior — cover the real-mode path (`signinSilent` called with the right scope, caching across calls) in a **separate** test file that never calls `enableMockAuth()`:

Create `shell/src/builder/copilot/useMcpTokenOidc.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const signinSilent = vi.fn().mockResolvedValue({ access_token: "real-mcp-token" });
vi.mock("react-oidc-context", () => ({ useAuth: () => ({ signinSilent }) }));

describe("useMcpToken (real OIDC mode)", () => {
  it("calls signinSilent with the geostudio-mcp-audience scope and caches the result", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const first = await result.current();
    expect(first).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledWith({ scope: "openid profile email geostudio-mcp-audience" });

    const second = await result.current();
    expect(second).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledTimes(1); // cached, not called again
  });

  it("throws a readable error when signinSilent resolves without a token", async () => {
    signinSilent.mockResolvedValueOnce(null);
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/copilot/useMcpToken.test.tsx src/builder/copilot/useMcpTokenOidc.test.tsx`
Expected: FAIL — `Cannot find module './useMcpToken'`.

- [ ] **Step 4: Implement**

Create `shell/src/builder/copilot/useMcpToken.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Jeton d'audience MCP distincte pour le copilote (SP-20) — obtenu via un
// second signinSilent() demandant le client-scope optionnel
// geostudio-mcp-audience (déjà provisionné dans le realm, Task 1), jamais
// via un paramètre resource ni token-exchange. Contourne délibérément le
// useAuth() de l'app (../../auth/useAuth), qui n'expose pas signinSilent —
// importe react-oidc-context directement, comme AuthProvider.tsx le fait
// déjà pour construire son propre <AuthProvider>. Le jeton ne vit qu'en
// mémoire (état React), jamais localStorage — même garantie que le jeton
// REST normal (cf. AuthProvider.tsx, InMemoryStore).
import { useCallback, useRef } from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { isMockMode } from "../../auth/useAuth";

const MCP_SCOPE = "openid profile email geostudio-mcp-audience";

export function useMcpToken(): () => Promise<string> {
  const cachedRef = useRef<string | null>(null);

  if (isMockMode()) {
    // mockMode est un drapeau au niveau module, fixé une fois avant tout
    // rendu (enableMockAuth() dans AuthProvider) — jamais togglé en cours
    // de vie de l'app, donc ce retour anticipé avant l'appel conditionnel
    // ci-dessous respecte quand même les rules-of-hooks en pratique, même
    // patron que useAuth.ts.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    return useCallback(async () => "mock-mcp-token", []);
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const oidc = useOidcAuth();
  return useCallback(async () => {
    if (cachedRef.current) return cachedRef.current;
    const user = await oidc.signinSilent({ scope: MCP_SCOPE });
    if (!user?.access_token) {
      throw new Error("Impossible d'obtenir un jeton MCP (signinSilent a échoué).");
    }
    cachedRef.current = user.access_token;
    return user.access_token;
  }, [oidc]);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/useMcpToken.test.tsx src/builder/copilot/useMcpTokenOidc.test.tsx`
Expected: PASS (all 3).

- [ ] **Step 6: Commit**

```bash
git add shell/src/auth/useAuth.ts shell/src/builder/copilot/useMcpToken.ts shell/src/builder/copilot/useMcpToken.test.tsx shell/src/builder/copilot/useMcpTokenOidc.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): useMcpToken — second signinSilent pour l'audience MCP (SP-20)

Demande le scope geostudio-mcp-audience (Task 1) via react-oidc-context
directement (useAuth() de l'app n'expose pas signinSilent). Jeton en
mémoire uniquement, mis en cache pour la session du panneau.
EOF
)"
```

---

## Task 11: Shell — `itemClient.ts` (`copilotTurn` + `copilotEnabled`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`

**Interfaces:**
- Produces: `InstanceInfo.copilotEnabled: boolean`; `CopilotMessage`, `CopilotClientOp`, `CopilotTurnResult` types; `ItemClient.copilotTurn(itemId, payload): Promise<CopilotTurnResult>`. Consumed by Task 13 (`CopilotPanel.tsx`) and `AppBuilderPage.tsx` wiring.

- [ ] **Step 1: Add types**

In `shell/src/api/types.ts`, change:
```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; appExportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean };
```
to:
```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; appExportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean; copilotEnabled: boolean };

export type CopilotMessage = { role: "user" | "assistant"; content: string };
export type CopilotClientOp = { op: string; args: Record<string, unknown> };
export type CopilotTurnResult = { reply: string; clientOps: CopilotClientOp[] };
export type CopilotToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };
```

Add the method to the `ItemClient` interface, right after `getInstanceInfo(): Promise<InstanceInfo>;`:
```ts
  getInstanceInfo(): Promise<InstanceInfo>;
  copilotTurn(itemId: string, payload: {
    message: string;
    history: CopilotMessage[];
    mcpToken: string;
    currentConfig: AppConfig;
    clientTools: CopilotToolSchema[];
  }): Promise<CopilotTurnResult>;
```

- [ ] **Step 2: Implement in `createItemClient`**

In `shell/src/api/itemClient.ts`, add right after `getAppExportJob`:

```ts
    async getAppExportJob(_itemId: string, jobId: string): Promise<AppExportJobStatus> {
      return request<AppExportJobStatus>("GET", `/app-exports/jobs/${jobId}`);
    },

    async copilotTurn(itemId, payload): Promise<CopilotTurnResult> {
      return request<CopilotTurnResult>("POST", "/copilot/turn", { itemId, ...payload });
    },
```

(Add `CopilotTurnResult` to the existing `import type { ... } from "./types"` at the top of the file.)

- [ ] **Step 3: Type-check**

Run: `cd shell && npm run build`
Expected: PASS — `tsc --noEmit` succeeds (confirms `createItemClient`'s returned object structurally satisfies the updated `ItemClient` interface, and any test-double `ItemClient` implementations using `Partial<ItemClient>` still compile).

- [ ] **Step 4: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts
git commit -m "$(cat <<'EOF'
feat(shell): ItemClient.copilotTurn + InstanceInfo.copilotEnabled (SP-20)

Types CopilotMessage/CopilotClientOp/CopilotTurnResult/CopilotToolSchema
et méthode copilotTurn() côté client, miroir de createAppExport.
EOF
)"
```

---

## Task 12: Shell — `CopilotPanel.tsx` + `AppBuilderPage.tsx` wiring

**Files:**
- Create: `shell/src/builder/copilot/CopilotPanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Create: `shell/src/builder/copilot/CopilotPanel.test.tsx`

**Interfaces:**
- Consumes: `useItemClient` (`../../api/ItemClientProvider`), `applyClientOp`/`RawClientOp` (Task 9), `buildClientToolSchemas` (Task 8), `useMcpToken` (Task 10), `Button` (`../../ui/button`).
- Produces: `CopilotPanel` component, mounted in `AppBuilderPage.tsx` gated on `copilotEnabled`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/copilot/CopilotPanel.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";
import { CopilotPanel } from "./CopilotPanel";

enableMockAuth();

function emptyConfig(): AppConfig {
  return {
    kind: "app", theme: {} as AppConfig["theme"], dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

function renderPanel(client: Partial<ItemClient>, setDraft: ReturnType<typeof vi.fn>) {
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <CopilotPanel itemId="1" config={emptyConfig()} activePageId="page-1" setDraft={setDraft} />
    </ItemClientProvider>,
  );
}

describe("CopilotPanel", () => {
  it("sends a message and shows the reply, without changing the draft when there are no clientOps", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockResolvedValue({ reply: "Ce dataset contient des incidents.", clientOps: [] });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(screen.getByText("Ce dataset contient des incidents.")).toBeInTheDocument());
    expect(setDraft).not.toHaveBeenCalled();
  });

  it("applies clientOps via a single setDraft call when present", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "J'ai ajouté un indicateur.",
      clientOps: [{ op: "addWidget", args: { type: "text" } }],
    });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Ajoute un widget texte");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(setDraft).toHaveBeenCalledTimes(1));
  });

  it("shows an error and does not crash when the request fails", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockRejectedValue(new Error("network"));
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx`
Expected: FAIL — `Cannot find module './CopilotPanel'`.

- [ ] **Step 3: Implement `CopilotPanel.tsx`**

Create `shell/src/builder/copilot/CopilotPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
// Panneau copilote du builder (SP-20) — propose des micro-actions
// (ajouter/modifier/retirer un widget, source de données, filtre) sur la
// config en cours d'édition. Chaque action passée par clientOps traverse
// setDraft (SP-19 undo) en un seul appel par tour : annulable via le
// bouton "Annuler" existant de la barre d'outils (AppBuilderPage.tsx),
// pas de bouton Annuler dédié ici — un seul et même undo stack.
import { useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AppConfig, CopilotMessage } from "../../api/types";
import { Button } from "../../ui/button";
import { applyClientOp, type RawClientOp } from "./applyClientOp";
import { buildClientToolSchemas } from "./clientTools";
import { useMcpToken } from "./useMcpToken";

const OP_LABELS: Record<string, string> = {
  addWidget: "Widget ajouté",
  updateWidgetProps: "Widget modifié",
  removeWidget: "Widget supprimé",
  addDataSource: "Source de données ajoutée",
  setFilter: "Filtre modifié",
};

export function CopilotPanel({
  itemId, config, activePageId, setDraft,
}: {
  itemId: string;
  config: AppConfig;
  activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  const [history, setHistory] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOpsSummary, setLastOpsSummary] = useState<string[]>([]);

  async function send() {
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    setError(null);
    const priorHistory = history;
    const nextHistory: CopilotMessage[] = [...priorHistory, { role: "user", content: message }];
    setHistory(nextHistory);
    try {
      const mcpToken = await getMcpToken();
      const result = await client.copilotTurn(itemId, {
        message, history: priorHistory, mcpToken, currentConfig: config,
        clientTools: buildClientToolSchemas(),
      });
      setHistory([...nextHistory, { role: "assistant", content: result.reply }]);
      if (result.clientOps.length > 0) {
        setLastOpsSummary(result.clientOps.map((o) => OP_LABELS[o.op] ?? `Action inconnue ignorée : ${o.op}`));
        setDraft((d) => {
          if (!d) return d;
          return (result.clientOps as RawClientOp[]).reduce(
            (acc, op) => applyClientOp(op, acc, activePageId), d,
          );
        });
      } else {
        setLastOpsSummary([]);
      }
    } catch {
      setError("Échec de la requête au copilote.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex max-h-64 flex-col gap-2 overflow-auto">
        {history.map((m, i) => (
          <p key={i} className={m.role === "user" ? "font-medium" : "text-slate-600"}>
            {m.content}
          </p>
        ))}
      </div>
      <label className="flex flex-col gap-1">
        <textarea
          aria-label="Message au copilote"
          className="min-h-16 rounded-md border border-slate-300 p-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
      </label>
      <Button size="sm" disabled={sending || !input.trim()} onClick={send}>
        Envoyer
      </Button>
      {lastOpsSummary.length > 0 && (
        <ul className="text-xs text-slate-500">
          {lastOpsSummary.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      )}
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Wire into `AppBuilderPage.tsx`**

Add the import (alphabetically, right after `import { AppExportPanel } from "../builder/appexport/AppExportPanel";`):
```ts
import { AppExportPanel } from "../builder/appexport/AppExportPanel";
import { CopilotPanel } from "../builder/copilot/CopilotPanel";
```

Add the flag derivation right after `const appExportEnabled = instanceQuery.data?.appExportEnabled === true;`:
```ts
  const appExportEnabled = instanceQuery.data?.appExportEnabled === true;
  const copilotEnabled = instanceQuery.data?.copilotEnabled === true;
```

Add the panel block right after the `appExportEnabled && (...)` block, still inside the left `<aside>`:

Change:
```tsx
              {appExportEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Export standalone</p>
                  <AppExportPanel itemId={pk} config={draft} />
                </>
              )}
            </aside>
```
to:
```tsx
              {appExportEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Export standalone</p>
                  <AppExportPanel itemId={pk} config={draft} />
                </>
              )}
              {copilotEnabled && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Copilote</p>
                  <CopilotPanel itemId={pk} config={draft} activePageId={activePage} setDraft={setDraft} />
                </>
              )}
            </aside>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx`
Expected: PASS (all 3).

Then the full shell suite + build:

Run: `cd shell && npm run build && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/copilot/CopilotPanel.tsx shell/src/builder/copilot/CopilotPanel.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): CopilotPanel — panneau de chat du builder (SP-20)

Monté dans AppBuilderPage.tsx, gated sur copilotEnabled. Applique les
clientOps en un seul setDraft (un tour = une entrée undo). Pas de bouton
Annuler dédié — réutilise le bouton Annuler existant de la barre d'outils
(un seul undo stack, SP-19).
EOF
)"
```

---

## Task 13: E2E — copilot panel presence + explain/add-widget flows

**Files:**
- Create: `shell/e2e/copilot.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`./mocks`), the existing app-creation flow (mirrors `shell/e2e/app-builder.spec.ts`).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/copilot.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("copilot panel is absent without copilotEnabled", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await expect(page.getByLabel("Message au copilote")).toHaveCount(0);
});

test("copilot: explain prompt makes no changes, add-widget prompt adds and is undoable", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  await page.route("https://core.test/copilot/turn", async (route) => {
    const body = route.request().postDataJSON() as { message: string };
    if (body.message.includes("indicateur")) {
      await route.fulfill({
        json: {
          reply: "J'ai ajouté un indicateur.",
          clientOps: [{ op: "addWidget", args: { type: "indicator" } }],
        },
      });
    } else {
      await route.fulfill({ json: { reply: "Ce dataset contient des incidents.", clientOps: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Explique — pas de changement de canevas.
  await page.getByLabel("Message au copilote").fill("Explique ce dataset");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("Ce dataset contient des incidents.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);

  // Ajoute un widget — apparaît sur le canevas, annulable via le bouton
  // Annuler de la barre d'outils (pas de bouton dédié dans le panneau).
  await page.getByLabel("Message au copilote").fill("Ajoute un indicateur");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("J'ai ajouté un indicateur.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();

  await page.getByRole("button", { name: "Annuler" }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);
});
```

- [ ] **Step 2: Run the spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/copilot.spec.ts`
Expected: PASS (both tests).

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS (all specs, including the new one — 19 specs total).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/copilot.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): panneau copilote — absence sans capacité, explication puis ajout de widget annulable (SP-20)
EOF
)"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-08-05-copilote-embarque-design.md`, as amended during the spec-verification pass):
- §2 architecture (shell → core → MCP loopback → clientOps back to shell): Tasks 4, 5, 9, 12.
- §2.1 MCP-audience bridge: Task 1 (realm), Task 10 (`useMcpToken`) — implemented as a client-scope grant, not `resource`/token-exchange, per the revised decision recorded in this session.
- §3 core components (`llm_provider.py`, `mcp_loopback.py`, `tools_allowlist.py`, `routes.py`, `GET /instance`): Tasks 2–5.
- §3 shell components (`CopilotPanel.tsx`, `useMcpToken.ts`, `clientTools.ts`, `applyClientOp.ts`): Tasks 8–12.
- §4 security (allowlist enforcement, no direct DB mutation, read-only-mode inheritance, in-memory-only token): Task 5 (allowlist check + read-only-guard exemption), Task 10 (in-memory token).
- §5 governance (off by default, no quota): Task 2 (`is_copilot_enabled`), Task 6 (env wiring).
- §6 out of scope: respected — no persistence beyond the browser session, no quotas, no full-dashboard generation, no runtime-mode copilot, no second LLM provider, no SQL Lab exposure beyond `run_analytics_query`.
- §7 risks: max-iteration guard (Task 5, tested), hallucinated-tool-argument mitigation (Task 9's `configSchema`-based coercion), SP-19 dependency (already shipped, confirmed at spec-verification time).
- §8 acceptance criteria: criterion 1 (Task 2 + `AppBuilderPage.tsx` gating), criterion 2 (Task 13 E2E "explain"), criterion 3 (Task 13 E2E "add widget", undoable via existing SP-19 button), criterion 4 (Task 5's read-only-guard exemption — MCP tools self-gate writes, matches `is_read_only_mode` already blocking `create_item`/`create_form_app` server-side), criterion 5 (Task 5's allowlist check, tested), criterion 6 (Task 5's max-iterations fallback, tested).

**Corrections made relative to the original design doc during this planning pass** (all grounded in reading the real code, not assumption):
1. §2.1's `resource` param / implied token-exchange replaced with a plain OIDC optional-scope grant (`geostudio-mcp-audience`, already provisioned in the realm) — simpler, no Keycloak preview feature required, confirmed against `deploy/keycloak/geostudio-realm.json`.
2. §3's "CopilotPanel is a tab, dedicated Annuler button calling `undo()` from a `UndoContext`" replaced with: CopilotPanel is a stacked always-visible panel (same as every other builder panel), and it has **no** dedicated Annuler button — it shares the single global undo stack via the toolbar's existing button, avoiding a duplicate-label collision.
3. `clientTools.ts`'s premise ("a new widget becomes automatically editable") required adding a new `configSchema` field to `WidgetDefinition` and backfilling all 22 builtin widgets (Task 7) — the registry previously had no declarative prop schema for builtin widgets, only for SP-8 WC/extension widgets.
4. `POST /copilot/turn` added to the read-only-mode middleware's exemption list (Task 5) — without this, acceptance criterion 4 (search/explain works in demo mode) would 403 before the handler ever ran.
5. `docker-compose.yml`/`​.env.example` wiring made an explicit task (Task 6) rather than assumed — `CORE_EMBEDDING_PROVIDER` (SP-7) never got this wiring and is silently inert in the packaged stack; not repeating that.

**Placeholder scan:** none found — every step has complete code, exact file paths, and expected command output. The one intentionally-flagged-and-then-corrected placeholder in Task 5 (`test_allowlisted_mcp_tool_call_is_executed_via_loopback`) is resolved inline with the real assertion to write, immediately following it.

**Type consistency:** `RawClientOp`/`ClientOp` (server Pydantic `op`/`args` ↔ shell `{op, args}`) match across Task 5 and Task 9. `CopilotTurnResponse{reply, clientOps}` (Task 5) matches `CopilotTurnResult{reply, clientOps}` (Task 11) and `CopilotPanel`'s usage (Task 12). `WidgetPropDescriptor{name, type, label, default}` (Task 7) is consumed identically in Task 8 (`clientTools.ts`) and Task 9 (`applyClientOp.ts`). `useMcpToken(): () => Promise<string>` (Task 10) matches its usage in `CopilotPanel` (Task 12: `const getMcpToken = useMcpToken(); ... await getMcpToken()`).
