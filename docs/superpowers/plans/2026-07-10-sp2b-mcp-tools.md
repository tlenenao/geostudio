# SP-2b — Outils MCP (catalogue, config, partage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Branch the 7 business tools (`list_items`, `get_item`, `get_app_config`, `save_app_config`, `create_item`, `get_sharing`, `set_sharing`) onto the `/mcp` endpoint SP-2a already authenticated, plus the `AppConfig`/`MapConfig` JSON Schema publication. Strict mirror of the existing REST API — same repository functions, same `can()` gate, same audit action names (with `actor_kind="agent"`).

**Architecture:** All 7 tools (plus the pre-existing `whoami`) move into `core/app/mcp/tools.py`'s `register_tools(server, session_factory)`, called once from `server.py`'s `create_mcp_server()` (currently `whoami` is defined inline there — Task 1 relocates it, no behavior change). Two small shared helpers live at the top of `tools.py`: `_resolve_actor(session, access_token) -> User` (the exact identity-resolution block `whoami` already has, extracted so every tool shares it) and `_require_access(session, *, user, item_id, action) -> ItemAccessFacts` (mirrors `app/configs/routes.py`'s existing `_require_access` — same 404-then-403 logic — but raises `ValueError` instead of `HTTPException`, since a `TokenVerifier`/MCP tool has no HTTP status channel; this is the same "duplicated deliberately, not shared, because the two surfaces must evolve independently" reasoning SP-2a already established for `_jwks_client()`). Tools call the same repository functions the REST routes call (`items_repo`, `configs_repo`, `sharing_repo`) — never the routes themselves, matching how `app.public`'s routes already do this. `app.mcp` sits at the top of the layering (established in SP-2a), so importing `app.items`/`app.configs`/`app.sharing` directly is already permitted.

**Tech Stack:** No new dependency — reuses `mcp` (SP-2a), the existing repository/schema modules, `Pydantic`'s `model_json_schema()`.

## Global Constraints

- Every tool that touches an existing item calls `_require_access` (or, for `list_items`, relies on `items_repo.list_items`'s existing server-side scope filtering — SP-1c) — never a parallel visibility check.
- A business-logic failure (invisible item, forbidden write, invalid config) is a normal Python exception (`ValueError`) raised from inside the tool body — the SDK's `Tool.run()` already catches any exception and surfaces it as `is_error=True` (confirmed against the SDK's source during the design spec's research) — no manual HTTP-style error construction.
- `create_item` never accepts an `owner` parameter — the owner is always the identity `_resolve_actor` resolves from the validated access token, matching the REST API's `POST /configs` behavior (itself fixed for the exact same reason back in SP-1c/A-something — owner is never client-supplied).
- Every write tool (`save_app_config`, `create_item`, `set_sharing`) calls `write_audit(..., actor_kind="agent", ...)` with the SAME action name its REST equivalent uses (`config.update`, `item.create`+`config.create`, `item.share`) — no new action vocabulary invented.
- No change to any existing REST route, to `app/auth/dependency.py`, or to `app/mcp/auth.py` (SP-2a's `TokenVerifier`s stay as they are).
- Interfaces this plan consumes (already merged): `app.items.repository.{get_access_facts, get_item, list_items, create_item}`, `app.configs.repository.{create_config, get_config_by_item, update_config, ConfigRead}`, `app.sharing.repository.{list_shares, replace_shares}`, `app.sharing.authorization.{can, ItemAccessFacts}`, `app.audit.writer.write_audit`, `app.mcp.auth.get_token_verifier`, `mcp.server.auth.middleware.auth_context.get_access_token`.

---

### Task 1: Shared helpers, relocate `whoami`, add `list_items`/`get_item`

**Files:**
- Create: `core/app/mcp/tools.py`
- Modify: `core/app/mcp/server.py`
- Create: `core/tests/test_mcp_tools_items.py`

**Interfaces:**
- Consumes: `app.items.repository.{get_access_facts, get_item, list_items}`, `app.sharing.authorization.can`, `app.tenants.repository.get_or_create_default_tenant`, `app.users.repository.get_or_create_user`.
- Produces: `app.mcp.tools.register_tools(server: FastMCP, session_factory) -> None` — registers `whoami`, `list_items`, `get_item`. `_resolve_actor(session, access_token) -> User` and `_require_access(session, *, user, item_id, action) -> ItemAccessFacts` (raises `ValueError` on 404/403-equivalent), both used by every later task's tools too.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_tools_items.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.items import repository as items_repo
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        # CORE_AUTH_MODE=mock always resolves this exact identity (see
        # app/auth/dependency.py's mock branch and MockTokenVerifier).
        mock_user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
            username="mockuser", email=None, first_name="Mock", last_name="User",
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
    return test_client


def call_tool(test_client, name: str, arguments: dict) -> dict:
    """Drives one full MCP handshake (initialize -> notifications/initialized
    -> tools/call) and returns the parsed tool result. Raises AssertionError
    with the tool's error text if the call itself errored (is_error=True) —
    call helper for a SUCCESSFUL call; use call_tool_expecting_error below
    for tests that want to assert on failure."""
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
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
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
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(
        line for line in call_response.text.splitlines() if line.startswith("data: ")
    )
    payload = json.loads(body_line.removeprefix("data: "))
    return payload["result"]


def _seed_item(test_client, *, owner_id, title="Item") -> str:
    with test_client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=test_client.tenant.id, owner_id=owner_id,
            resource_type="app", title=title,
        )
        session.commit()
        return item.id


def test_list_items_returns_owned_items(app_client):
    _seed_item(app_client, owner_id=app_client.mock_user.id, title="Mine")

    with app_client:
        result = call_tool(app_client, "list_items", {"scope": "mine"})

    assert result["total"] == 1
    assert result["items"][0]["title"] == "Mine"


def test_get_item_returns_owned_item(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id, title="Mine")

    with app_client:
        result = call_tool(app_client, "get_item", {"itemId": item_id})

    assert result["title"] == "Mine"
    assert result["owner"] == "mockuser"


def test_get_item_invisible_to_a_stranger_errors(app_client):
    with app_client.session_factory() as session:
        stranger = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="sub-stranger",
            username="stranger", email=None, first_name="", last_name="",
        )
        session.commit()
        stranger_id = stranger.id
    item_id = _seed_item(app_client, owner_id=stranger_id, title="Not mine")

    with app_client:
        error_text = call_tool_expecting_error(app_client, "get_item", {"itemId": item_id})

    assert "not found" in error_text.lower()


def test_get_item_visible_via_group_share_succeeds(app_client):
    with app_client.session_factory() as session:
        owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="sub-owner",
            username="owner", email=None, first_name="", last_name="",
        )
        session.flush()
        item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=owner.id,
            resource_type="app", title="Shared",
        )
        group = Group(id="g1", tenant_id=app_client.tenant.id, name="G", created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=app_client.mock_user.id, tenant_id=app_client.tenant.id))
        session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=app_client.tenant.id, role="viewer"))
        session.commit()
        item_id = item.id

    with app_client:
        result = call_tool(app_client, "get_item", {"itemId": item_id})

    assert result["title"] == "Shared"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_items.py -v`
Expected: FAIL — `list_items`/`get_item` tools don't exist yet (`tools/call` for an unknown tool name returns an MCP protocol error, not the shape these tests expect).

- [ ] **Step 4: Create `app/mcp/tools.py`**

```python
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.db import request_scoped_session
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.sharing.authorization import ItemAccessFacts, can
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def _resolve_actor(session, access_token) -> User:
    claims = access_token.claims
    tenant = get_or_create_default_tenant(session)
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=access_token.subject,
        username=claims.get("preferred_username", access_token.subject),
        email=claims.get("email"),
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
    )


def _require_access(session, *, user: User, item_id: str, action: str) -> ItemAccessFacts:
    """Mirrors app/configs/routes.py's _require_access — same 404-then-403
    logic — but raises ValueError (a normal tool-body exception the SDK
    turns into an is_error result) instead of HTTPException, since a
    TokenVerifier-authenticated MCP tool has no HTTP status channel."""
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise ValueError("item not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise ValueError("not allowed to modify this item")
    return facts


def register_tools(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def whoami(ctx: Context) -> dict:
        """Return the identity of the currently authenticated MCP caller —
        proves the OAuth handshake resolves to the same User the shell's
        REST API would resolve for the same Keycloak subject."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            return {"username": user.username, "tenantId": user.tenant_id}

    @server.tool()
    async def list_items(
        ctx: Context,
        q: str | None = None,
        type: str | None = None,
        scope: str = "all",
        page: int = 1,
        pageSize: int = 12,
    ) -> ItemPage:
        """List catalog items — mirrors GET /items. scope: all|mine|shared|public."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            return items_repo.list_items(
                session, tenant_id=user.tenant_id, current_user_id=user.id,
                q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
            )

    @server.tool()
    async def get_item(ctx: Context, itemId: str) -> ItemRead:
        """Get one catalog item by id — mirrors GET /items/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="read")
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=itemId)
            if result is None:
                raise ValueError("item not found")
            return result
```

- [ ] **Step 5: Update `app/mcp/server.py`**

Remove `whoami`'s inline definition and the now-unused imports (`get_or_create_default_tenant`, `get_or_create_user`, `get_access_token`, `request_scoped_session`, `Context`), replacing with a call to `register_tools`:

```python
import os

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from app.mcp.auth import get_token_verifier
from app.mcp.tools import register_tools


def create_mcp_server(base_url: str, session_factory) -> FastMCP:
    """base_url is the cœur's own externally-reachable URL, e.g.
    http://localhost:8200 — used to build the /mcp resource identifier and
    (indirectly, via AuthSettings) the RFC 9728 metadata document."""
    server = FastMCP(
        "GeoStudio",
        instructions="GeoStudio cœur MCP endpoint.",
        token_verifier=get_token_verifier(),
        auth=AuthSettings(
            issuer_url=os.environ.get(
                "CORE_OIDC_ISSUER", "http://localhost:8180/realms/geostudio"
            ),
            required_scopes=[],
            resource_server_url=f"{base_url}/mcp",
        ),
    )
    register_tools(server, session_factory)
    return server
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_items.py tests/test_mcp_routes.py -v`
Expected: PASS — the new tests AND SP-2a's existing `test_mcp_routes.py` (whoami must still work identically after the relocation).

- [ ] **Step 7: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/mcp/tools.py core/app/mcp/server.py core/tests/test_mcp_tools_items.py
git commit -m "feat(core): MCP list_items/get_item tools; relocate whoami into tools.py"
```

---

### Task 2: `get_app_config` / `save_app_config`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Create: `core/tests/test_mcp_tools_configs.py`

**Interfaces:**
- Consumes: `app.configs.repository.{get_config_by_item, update_config, ConfigRead}`, `app.configs.schemas.BuilderConfig`, `app.audit.writer.write_audit`.
- Produces: two more tools registered by `register_tools`.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_tools_configs.py` — reuse the exact `app_client`/`call_tool`/`call_tool_expecting_error`/`call_tool_raw`/`_seed_item` helpers from `test_mcp_tools_items.py` (copy them verbatim into this file too, matching the existing codebase convention of per-test-file fixture duplication rather than a shared conftest for these — see how `test_routes.py` and `test_items_routes.py` each define their own `client` fixture independently):

```python
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# ... app_client fixture, call_tool/call_tool_expecting_error/call_tool_raw,
# _seed_item — identical to test_mcp_tools_items.py, copy verbatim ...


def _config_body(widget="map") -> dict:
    return {
        "kind": "app",
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    }


def _seed_config(test_client, *, owner_id, title="Item") -> tuple[str, str]:
    with test_client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=test_client.tenant.id, owner_id=owner_id,
            resource_type="app", title=title,
        )
        session.flush()
        config = configs_repo.create_config(session, BuilderConfig(**_config_body()), item_id=item.id)
        session.commit()
        return item.id, config.id


def test_get_app_config_returns_owned_item_config(app_client):
    item_id, _ = _seed_config(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        result = call_tool(app_client, "get_app_config", {"itemId": item_id})

    assert result["config"]["layout"]["items"][0]["widget"] == "map"


def test_save_app_config_updates_and_bumps_version(app_client):
    item_id, _ = _seed_config(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        result = call_tool(
            app_client, "save_app_config",
            {"itemId": item_id, "config": _config_body(widget="table")},
        )

    assert result["version"] == 2
    assert result["config"]["layout"]["items"][0]["widget"] == "table"


def test_save_app_config_by_group_viewer_errors(app_client):
    from app.sharing.models import Group, GroupMember, ItemShare

    with app_client.session_factory() as session:
        owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="sub-owner",
            username="owner", email=None, first_name="", last_name="",
        )
        session.flush()
        item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=owner.id,
            resource_type="app", title="Shared",
        )
        session.flush()
        configs_repo.create_config(session, BuilderConfig(**_config_body()), item_id=item.id)
        group = Group(id="g1", tenant_id=app_client.tenant.id, name="G", created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=app_client.mock_user.id, tenant_id=app_client.tenant.id))
        session.add(ItemShare(item_id=item.id, group_id=group.id, tenant_id=app_client.tenant.id, role="viewer"))
        session.commit()
        item_id = item.id

    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "save_app_config", {"itemId": item_id, "config": _config_body(widget="table")},
        )

    assert "not allowed" in error_text.lower()


def test_save_app_config_writes_audit_log_with_agent_actor(app_client):
    item_id, _ = _seed_config(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        call_tool(app_client, "save_app_config", {"itemId": item_id, "config": _config_body()})

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = session.scalars(select(AuditLog).where(AuditLog.action == "config.update")).all()
        assert len(rows) == 1
        assert rows[0].actor_kind == "agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_configs.py -v`
Expected: FAIL — tools don't exist yet.

- [ ] **Step 3: Add the two tools to `register_tools` in `app/mcp/tools.py`**

Add these imports to the top of the file:
```python
from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.configs.schemas import BuilderConfig
```

Add inside `register_tools`, after `get_item`:
```python
    @server.tool()
    async def get_app_config(ctx: Context, itemId: str) -> ConfigRead:
        """Get the app/dashboard config for an item — mirrors GET /configs/by-item/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="read")
            result = configs_repo.get_config_by_item(session, itemId)
            if result is None:
                raise ValueError("config not found")
            return result

    @server.tool()
    async def save_app_config(ctx: Context, itemId: str, config: BuilderConfig) -> ConfigRead:
        """Save (and version) the app/dashboard config for an item — mirrors
        PUT /configs/by-item/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="write")
            existing = configs_repo.get_config_by_item(session, itemId)
            if existing is None:
                raise ValueError("config not found")
            result = configs_repo.update_config(session, existing.id, config)
            if result is None:
                raise ValueError("config not found")
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.update", object_type="config", object_id=existing.id, payload={},
            )
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_configs.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_configs.py
git commit -m "feat(core): MCP get_app_config/save_app_config tools"
```

---

### Task 3: `create_item`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Create: `core/tests/test_mcp_tools_create.py`

**Interfaces:**
- Consumes: `app.items.repository.create_item`, `app.configs.repository.create_config`.
- Produces: `create_item` tool.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_tools_create.py` (copy the same `app_client`/`call_tool*` helpers from Task 1's test file verbatim):

```python
def test_create_item_creates_and_owns_it_as_the_caller(app_client):
    with app_client:
        result = call_tool(
            app_client, "create_item",
            {
                "kind": "app", "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    assert result["title"] == "My App"
    assert result["owner"] == "mockuser"

    with app_client.session_factory() as session:
        from app.items.models import Item
        item = session.get(Item, result["pk"])
        assert item.owner_id == app_client.mock_user.id


def test_create_item_ignores_any_owner_argument_and_uses_the_caller_identity(app_client):
    # create_item's tool signature has no `owner` parameter at all — the
    # owner is always _resolve_actor's identity. This test proves that
    # invariant holds even if a permissive MCP client tries to smuggle an
    # extra "owner" argument in: whether the SDK's argument validation
    # rejects the unknown field outright (is_error=True) or silently drops
    # it (call succeeds), no item is ever created with the spoofed owner —
    # that's the actual guarantee, independent of which validation behavior
    # the SDK has (not asserted here; if this needs pinning down, check by
    # running the call once with print(result) before finishing this test).
    with app_client:
        call_tool_raw(
            app_client, "create_item",
            {
                "kind": "app", "title": "My App", "owner": "someone-else",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    with app_client.session_factory() as session:
        from app.items.models import Item
        from sqlalchemy import select
        spoofed = session.scalars(select(Item).where(Item.owner_id == "someone-else")).all()
        assert spoofed == []


def test_create_item_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        call_tool(
            app_client, "create_item",
            {
                "kind": "app", "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        rows = list(session.scalars(select(AuditLog)))
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_create.py -v`
Expected: FAIL — tool doesn't exist yet.

- [ ] **Step 3: Add `create_item` to `register_tools`**

Add this import to the top of `tools.py`:
```python
from typing import Literal
```

Add inside `register_tools`, after `save_app_config`:
```python
    @server.tool()
    async def create_item(
        ctx: Context, kind: Literal["app", "dashboard"], title: str, config: BuilderConfig,
    ) -> ItemRead:
        """Create a new app or dashboard — mirrors POST /configs. The item's
        owner is always the authenticated caller; there is no owner
        parameter to accept from the agent."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type=kind, title=title,
            )
            config_result = configs_repo.create_config(session, config, item_id=item.id)
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": kind},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None  # just created it, in the same transaction
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_create.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_create.py
git commit -m "feat(core): MCP create_item tool"
```

---

### Task 4: `get_sharing` / `set_sharing`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Create: `core/tests/test_mcp_tools_sharing.py`

**Interfaces:**
- Consumes: `app.sharing.repository.{list_shares, replace_shares}`, `app.sharing.schemas.{Sharing, GroupShare}`.
- Produces: `get_sharing`, `set_sharing` tools.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_tools_sharing.py` (copy the same helpers):

```python
def test_get_sharing_defaults_to_private(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        result = call_tool(app_client, "get_sharing", {"itemId": item_id})

    assert result == {"public": False, "groups": []}


def test_set_sharing_then_get_sharing_round_trips(app_client):
    from app.sharing.models import Group

    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    with app_client.session_factory() as session:
        session.add(Group(id="g1", tenant_id=app_client.tenant.id, name="G", created_by=app_client.mock_user.id))
        session.commit()

    with app_client:
        call_tool(
            app_client, "set_sharing",
            {"itemId": item_id, "sharing": {"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]}},
        )
        result = call_tool(app_client, "get_sharing", {"itemId": item_id})

    assert result == {"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]}


def test_set_sharing_with_unknown_group_errors(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "set_sharing",
            {"itemId": item_id, "sharing": {"public": False, "groups": [{"groupId": "nope", "role": "viewer"}]}},
        )

    assert "group" in error_text.lower()


def test_set_sharing_writes_audit_log_with_agent_actor(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        call_tool(app_client, "set_sharing", {"itemId": item_id, "sharing": {"public": True, "groups": []}})

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = session.scalars(select(AuditLog).where(AuditLog.action == "item.share")).all()
        assert len(rows) == 1
        assert rows[0].actor_kind == "agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_sharing.py -v`
Expected: FAIL — tools don't exist yet.

- [ ] **Step 3: Add `get_sharing`/`set_sharing` to `register_tools`**

Add these imports to the top of `tools.py`:
```python
from app.sharing import repository as sharing_repo
from app.sharing.schemas import Sharing
```

Add inside `register_tools`, after `create_item`:
```python
    @server.tool()
    async def get_sharing(ctx: Context, itemId: str) -> Sharing:
        """Get an item's sharing settings — mirrors GET /items/{id}/sharing."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            facts = _require_access(session, user=user, item_id=itemId, action="read")
            shares = sharing_repo.list_shares(session, item_id=itemId)
            return Sharing(
                public=facts.is_public,
                groups=[{"groupId": s.group_id, "role": s.role} for s in shares],
            )

    @server.tool()
    async def set_sharing(ctx: Context, itemId: str, sharing: Sharing) -> None:
        """Set an item's sharing settings — mirrors PUT /items/{id}/sharing."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="share")
            ok = sharing_repo.replace_shares(
                session, tenant_id=user.tenant_id, item_id=itemId,
                shares=[(g.groupId, g.role) for g in sharing.groups],
            )
            if not ok:
                raise ValueError("group not found")
            items_repo.set_is_public(session, tenant_id=user.tenant_id, item_id=itemId, is_public=sharing.public)
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.share", object_type="item", object_id=itemId,
                payload={"public": sharing.public, "groups": [g.model_dump() for g in sharing.groups]},
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_sharing.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_sharing.py
git commit -m "feat(core): MCP get_sharing/set_sharing tools"
```

---

### Task 5: JSON Schema — MCP resource + HTTP endpoint

**Files:**
- Modify: `core/app/mcp/tools.py`
- Create: `core/app/schemas_routes.py`
- Modify: `core/app/main.py`
- Create: `core/tests/test_mcp_schema.py`

**Interfaces:**
- Consumes: `app.configs.schemas.BuilderConfig.model_json_schema()`.
- Produces: MCP resource `schema://app-config`; `GET /schemas/app-config`.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_schema.py`:
```python
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session


def test_schema_http_endpoint_returns_builder_config_json_schema(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    response = client.get("/schemas/app-config")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "BuilderConfig"
    assert "properties" in body
    engine.dispose()
```

(The MCP resource itself — `schema://app-config` — is exercised by the manual verification in Task 6, since testing MCP *resources* via the raw JSON-RPC handshake this codebase's tool tests use would require a `resources/read` request shape not yet exercised anywhere in this test suite; the HTTP endpoint test above already proves the underlying schema generation is correct, and both the resource and the endpoint call the exact same `BuilderConfig.model_json_schema()` — see Step 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_schema.py -v`
Expected: FAIL — `/schemas/app-config` doesn't exist yet (404).

- [ ] **Step 3: Add the MCP resource to `register_tools`**

Add this import to the top of `tools.py`:
```python
from app.configs.schemas import BuilderConfig
```
(if not already imported by an earlier task — check before adding a duplicate).

Add inside `register_tools`, after `set_sharing`:
```python
    @server.resource("schema://app-config")
    def app_config_schema() -> dict:
        """JSON Schema for AppConfig/DashboardConfig — validate before
        calling create_item or save_app_config."""
        return BuilderConfig.model_json_schema()
```

- [ ] **Step 4: Create the HTTP endpoint**

`core/app/schemas_routes.py`:
```python
from fastapi import APIRouter

from app.configs.schemas import BuilderConfig

router = APIRouter()


@router.get("/schemas/app-config")
def get_app_config_schema() -> dict:
    return BuilderConfig.model_json_schema()
```

In `core/app/main.py`, add the import and registration next to the other routers:
```python
from app.schemas_routes import router as schemas_router
```
```python
    app.include_router(schemas_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_schema.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS. `app/schemas_routes.py` sits at the same layer as `app/public/routes.py` (imports only `app.configs`) — no contract change needed, it's a leaf module like the others directly under `app.main`.

- [ ] **Step 7: Commit**

```bash
git add core/app/mcp/tools.py core/app/schemas_routes.py core/app/main.py core/tests/test_mcp_schema.py
git commit -m "feat(core): publish AppConfig JSON Schema (MCP resource + HTTP endpoint)"
```

---

### Task 6: Manual verification doc, full stack smoke test

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: a documented manual verification procedure for the full roadmap demo scenario.

- [ ] **Step 1: Add the manual verification section to `README.md`**

After the existing "Vérifier le serveur MCP (manuel)" section (added by SP-2a), extend it — do not duplicate the section header, add a new subsection:

```markdown
#### Scénario complet (SP-2b) : créer un dashboard depuis un agent

Une fois connecté (voir ci-dessus), un agent MCP peut maintenant :

1. `list_items` — lister le catalogue.
2. `get_app_config` sur un item existant — lire sa config.
3. Lire la ressource `schema://app-config` (ou `GET /schemas/app-config`)
   pour connaître la forme attendue d'un `AppConfig`.
4. `create_item` avec un config valide contre ce schéma — crée un nouveau
   dashboard, dont l'owner est l'utilisateur Keycloak connecté (jamais un
   paramètre de l'outil).
5. Ouvrir http://localhost:8300 dans le shell, se connecter avec le même
   utilisateur : le dashboard créé par l'agent apparaît dans le catalogue et
   s'ouvre normalement dans le builder — c'est le critère d'acceptation
   final de la feuille de route pour SP-2 (« un agent crée un dashboard
   valide qui s'ouvre dans le builder »).
6. Vérifier `audit_log` (via un accès direct à la base, ou un futur outil
   d'administration) : les lignes créées par cette séquence portent
   `actor_kind = "agent"`, pas `"user"`.
```

- [ ] **Step 2: Full stack smoke test**

Run:
```bash
docker compose up -d
docker compose ps
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm test
docker compose down
```
Expected: all green, no regression in the shell (this plan touches no shell code).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the full SP-2b agent-creates-a-dashboard verification scenario"
```
