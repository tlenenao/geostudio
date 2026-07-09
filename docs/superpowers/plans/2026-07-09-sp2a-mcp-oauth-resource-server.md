# SP-2a — Serveur de ressources OAuth pour le MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a minimal, authenticated MCP endpoint (`/mcp`) in the cœur — the OAuth 2.1 + PKCE handshake (spec *MCP Authorization*), Dynamic Client Registration against Keycloak, and a dedicated `geostudio-mcp` token audience — with zero real business tools. SP-2b plugs the actual tools (`list_items`, `get_item`, etc.) into this already-authenticated base.

**Architecture:** New `core/app/mcp/` package at the top of the layering (`app.main → app.mcp → app.public → app.configs → app.items → app.sharing → app.auth → app.audit → app.users → app.tenants`). The official `mcp` Python SDK's `MCPServer` class (transport `streamable-http`) is mounted as an ASGI sub-app at `/mcp` on the existing FastAPI app, configured with `AuthSettings(issuer_url=CORE_OIDC_ISSUER, resource_server_url=.../mcp)` and a custom `TokenVerifier` — the SDK then generates the RFC 9728 protected-resource-metadata endpoint and the `401`+`WWW-Authenticate` challenge automatically; **this plan does not hand-write either of those**, confirmed against the SDK's source (`mcp.server.auth.routes.create_protected_resource_routes`/`build_resource_metadata_url`). The `TokenVerifier` (`core/app/mcp/auth.py`) mirrors `app/auth/dependency.py`'s JWT validation logic exactly (same `PyJWKClient`, same issuer) but checks a separate `CORE_MCP_AUDIENCE` (default `geostudio-mcp`) instead of `CORE_OIDC_AUDIENCE` — deliberately duplicated rather than parameterized, so the shell's REST API auth and the MCP endpoint's auth can evolve independently. On the Keycloak side, DCR only works once a default-blocking `Trusted Hosts` anonymous registration policy (present on the realm since its creation, confirmed by live testing during this plan's research) is removed, and a new `geostudio-mcp-audience` client scope, marked realm-**default**, is what gives every dynamically-registered client the right audience automatically — confirmed live: the realm-level bulk `PUT .../realms/{realm}` does **not** persist `defaultDefaultClientScopes` (a REST API quirk), the dedicated `PUT .../realms/{realm}/default-default-client-scopes/{scopeId}` endpoint does.

**Tech Stack:** `mcp` (official Python SDK, `>=1.12`), reusing `pyjwt[crypto]` (already a cœur dependency) for the custom `TokenVerifier`. No new infrastructure — Keycloak already runs (SP-1d.2).

## Global Constraints

- Zero real business tools in this plan — one `whoami` tool only, whose entire purpose is proving the authenticated-request → resolved-`User` loop works, not delivering a capability. `list_items`/`get_item`/etc. are SP-2b.
- `CORE_MCP_AUDIENCE` (default `geostudio-mcp`) is a **distinct** audience from `CORE_OIDC_AUDIENCE` (`geostudio-core`) — a token valid for the shell's REST API must be rejected on `/mcp`, and vice versa.
- Mock mode (`CORE_AUTH_MODE=mock`) must keep working for `/mcp` with zero Keycloak dependency, symmetric with `get_current_user`'s existing mock branch (same `mockuser`/`mock-sub` identity).
- The realm's DCR policy relaxation (removing the empty-list `Trusted Hosts` anonymous policy) is an explicit, documented v0 tradeoff for a dev-only, mono-tenant realm — not something to silently harden or silently leave broken; call it out in the realm JSON's own tracking (git commit message) and in this plan's risk section.
- No change to `app/auth/dependency.py`, `get_current_user`, or any existing REST route — this plan only adds a new, independent authenticated surface.
- Interfaces this plan consumes (already merged): `app.auth.dependency`'s JWT-validation pattern (`_jwks_client()`, `jwt.decode(...)` shape) as a reference to mirror, not to import; `app.users.repository.get_or_create_user(session, *, tenant_id, oidc_sub, username, email, first_name, last_name) -> User`; `app.tenants.repository.get_or_create_default_tenant(session) -> Tenant`; `deploy/keycloak/geostudio-realm.json` (realm `geostudio`, already validated end-to-end in SP-1d.2).

---

### Task 1: Keycloak realm — enable DCR, add the `geostudio-mcp` default audience scope

**Files:**
- Modify: `deploy/keycloak/geostudio-realm.json`

**Interfaces:**
- Consumes: nothing new.
- Produces: any client dynamically registered against the `geostudio` realm (anonymous DCR, RFC 7591) automatically receives an access-token audience mapper adding `geostudio-mcp`.

- [ ] **Step 1: Remove the blocking `Trusted Hosts` anonymous client-registration policy**

In `deploy/keycloak/geostudio-realm.json`, find the `components` → `"org.keycloak.services.clientregistration.policy.ClientRegistrationPolicy"` array and remove the entry with `"name": "Trusted Hosts"` / `"subType": "anonymous"` (id `16e6d92c-5595-4175-9b8d-97f4c62db712` in the current file — confirm the id matches before deleting; if the file has drifted, locate it by `"providerId": "trusted-hosts"` and `"subType": "anonymous"` instead):
```json
{
  "id": "16e6d92c-5595-4175-9b8d-97f4c62db712",
  "name": "Trusted Hosts",
  "providerId": "trusted-hosts",
  "subType": "anonymous",
  "subComponents": {},
  "config": {
    "host-sending-registration-request-must-match": ["true"],
    "client-uris-must-match": ["true"]
  }
}
```
Delete this entire object from the array (keep the array's other entries — `Allowed Protocol Mapper Types`, `Consent Required`, `Allowed Client Scopes`, etc. — untouched; the empty-list `Trusted Hosts` policy is the only one that unconditionally rejects every anonymous registration, confirmed by live testing: `POST /realms/{realm}/clients-registrations/openid-connect` returns `403 Policy 'Trusted Hosts' rejected request... Host not trusted` with this policy present, and succeeds once it's removed).

- [ ] **Step 2: Add the `geostudio-mcp-audience` client scope**

In the same file's `clientScopes` array, add a new entry (model it on the existing `acr` entry's shape, already in the file):
```json
{
  "id": "a1b2c3d4-0000-4000-8000-000000000001",
  "name": "geostudio-mcp-audience",
  "description": "Adds geostudio-mcp to the access token audience for MCP clients",
  "protocol": "openid-connect",
  "attributes": {
    "include.in.token.scope": "false",
    "display.on.consent.screen": "false"
  },
  "protocolMappers": [
    {
      "id": "a1b2c3d4-0000-4000-8000-000000000002",
      "name": "geostudio-mcp-audience-mapper",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-audience-mapper",
      "consentRequired": false,
      "config": {
        "included.custom.audience": "geostudio-mcp",
        "id.token.claim": "false",
        "access.token.claim": "true"
      }
    }
  ]
}
```
(Use fresh random UUIDs, not the literal placeholders above — any tool that generates v4 UUIDs is fine, e.g. `python3 -c "import uuid; print(uuid.uuid4())"`.)

- [ ] **Step 3: Mark the new scope as a realm-default client scope**

Add `"geostudio-mcp-audience"` to the `defaultDefaultClientScopes` array (currently `["role_list", "profile", "email", "roles", "web-origins", "acr"]`):
```json
"defaultDefaultClientScopes": ["role_list", "profile", "email", "roles", "web-origins", "acr", "geostudio-mcp-audience"],
```

- [ ] **Step 4: Cold-import validation — realm import, then verify the default-scope attachment actually took effect**

This is the step that catches the REST-API-vs-import discrepancy found during this plan's research (a live `PUT` on the realm silently drops `defaultDefaultClientScopes`; a fresh **import** of the full realm representation is a different code path and is expected to honor it — but confirm, don't assume):

```bash
docker rm -f kc-sp2a-validate 2>/dev/null
docker run -d --name kc-sp2a-validate -p 8182:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=validate-pw \
  -v "$(pwd)/deploy/keycloak/geostudio-realm.json:/opt/keycloak/data/import/geostudio-realm.json:ro" \
  quay.io/keycloak/keycloak:24.0 start-dev --import-realm
sleep 25
docker logs kc-sp2a-validate 2>&1 | grep -i "realm.*imported\|error"
```
Expected: `Realm 'geostudio' imported` in the logs, no error.

Then get an admin token and check the default scope list directly:
```bash
TOKEN=$(curl -s -X POST http://localhost:8182/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=validate-pw" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s "http://localhost:8182/admin/realms/geostudio/default-default-client-scopes" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print([s['name'] for s in json.load(sys.stdin)])"
```
Expected: `geostudio-mcp-audience` appears in the list. **If it does not**, the JSON field alone isn't sufficient on import either — attach it via the dedicated endpoint as a one-time fixup instead, and note this discrepancy plainly in your report (don't silently work around it):
```bash
SCOPE_ID=$(curl -s "http://localhost:8182/admin/realms/geostudio/client-scopes" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import json,sys; print([s['id'] for s in json.load(sys.stdin) if s['name']=='geostudio-mcp-audience'][0])")
curl -s -X PUT "http://localhost:8182/admin/realms/geostudio/default-default-client-scopes/$SCOPE_ID" \
  -H "Authorization: Bearer $TOKEN" -w "\nHTTP %{http_code}\n"
```
(If this fallback is needed in a real deployment, it means the JSON-only approach is insufficient and Task 3's README/setup instructions must say so explicitly — reflect that back into this plan file too before moving on.)

- [ ] **Step 5: Live DCR test — confirm a dynamically-registered client actually inherits the audience scope**

```bash
curl -s -X POST http://localhost:8182/realms/geostudio/clients-registrations/openid-connect \
  -H "Content-Type: application/json" \
  -d '{"client_name": "sp2a-validation-client", "redirect_uris": ["http://localhost:9999/callback"], "grant_types": ["authorization_code"], "response_types": ["code"], "token_endpoint_auth_method": "none"}' \
  > /tmp/sp2a_dcr_test.json
cat /tmp/sp2a_dcr_test.json
CLIENT_ID=$(python3 -c "import json; print(json.load(open('/tmp/sp2a_dcr_test.json'))['client_id'])")
CLIENT_UUID=$(curl -s "http://localhost:8182/admin/realms/geostudio/clients?clientId=$CLIENT_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
curl -s "http://localhost:8182/admin/realms/geostudio/clients/$CLIENT_UUID/default-client-scopes" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print([s['name'] for s in json.load(sys.stdin)])"
```
Expected: `geostudio-mcp-audience` appears in this NEW client's default-client-scopes list — proof the mechanism works for real DCR clients, not just pre-existing ones.

- [ ] **Step 6: Tear down**

```bash
docker rm -f kc-sp2a-validate
rm -f /tmp/sp2a_dcr_test.json
```

- [ ] **Step 7: Commit**

```bash
git add deploy/keycloak/geostudio-realm.json
git commit -m "feat: enable anonymous DCR and add the geostudio-mcp default audience scope

Removes the empty-list Trusted Hosts anonymous client-registration
policy (blocked every anonymous DCR attempt unconditionally, confirmed
live) and adds geostudio-mcp-audience as a realm-default client scope,
so any dynamically-registered MCP client automatically gets
geostudio-mcp in its access token audience. Accepted v0 tradeoff for
a dev-only, mono-tenant realm — revisit before any public exposure."
```

---

### Task 2: `TokenVerifier` implementations — Keycloak JWKS + mock

**Files:**
- Create: `core/app/mcp/__init__.py`, `core/app/mcp/auth.py`
- Create: `core/tests/test_mcp_auth.py`
- Modify: `core/pyproject.toml` (add `mcp` dependency)

**Interfaces:**
- Consumes: `jwt.PyJWKClient` (same pattern as `app/auth/dependency.py`), `mcp.server.auth.provider.{AccessToken, TokenVerifier}`.
- Produces: `app.mcp.auth.KeycloakTokenVerifier` and `app.mcp.auth.MockTokenVerifier`, both implementing `TokenVerifier.verify_token(token: str) -> AccessToken | None`.

- [ ] **Step 1: Add the `mcp` dependency**

In `core/pyproject.toml`'s `dependencies` list, add:
```toml
    "mcp>=1.12",
```
Run: `cd core && uv sync`

- [ ] **Step 2: Write the failing tests**

`core/tests/test_mcp_auth.py`:
```python
import os

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app.mcp import auth as mcp_auth


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


@pytest.fixture()
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_token(private_key, *, audience="geostudio-mcp", issuer="https://keycloak.example/realms/geostudio", **claims):
    payload = {"sub": "sub-123", "aud": audience, "iss": issuer, **claims}
    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.mark.anyio
async def test_keycloak_verifier_accepts_valid_mcp_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    token = _make_token(private_key, preferred_username="alice")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is not None
    assert result.subject == "sub-123"
    assert result.claims["preferred_username"] == "alice"


@pytest.mark.anyio
async def test_keycloak_verifier_rejects_rest_api_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    # A token valid for the shell's REST API (audience geostudio-core) must
    # NOT be accepted here — the two surfaces have distinct audiences.
    token = _make_token(private_key, audience="geostudio-core")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is None


@pytest.mark.anyio
async def test_keycloak_verifier_rejects_wrong_issuer(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    token = _make_token(private_key, issuer="https://someone-else.example/realms/other")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is None


@pytest.mark.anyio
async def test_mock_verifier_always_resolves_mock_subject():
    verifier = mcp_auth.MockTokenVerifier()
    result = await verifier.verify_token("anything-at-all")

    assert result is not None
    assert result.subject == "mock-sub"


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp'`.

- [ ] **Step 4: Write `app/mcp/auth.py`**

`core/app/mcp/__init__.py`: empty file.

`core/app/mcp/auth.py`:
```python
import os
from functools import lru_cache

import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    # Deliberately duplicated from app.auth.dependency._jwks_client rather
    # than imported — the two auth surfaces (shell REST API vs. MCP) must be
    # free to evolve independently (see plan Architecture).
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get(
        "CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"
    )
    return jwt.PyJWKClient(jwks_url, lifespan=600)


class KeycloakTokenVerifier(TokenVerifier):
    """Validates MCP bearer tokens against CORE_MCP_AUDIENCE — a distinct
    audience from CORE_OIDC_AUDIENCE, so a token valid for the shell's REST
    API is never valid here, and vice versa."""

    async def verify_token(self, token: str) -> AccessToken | None:
        issuer = os.environ["CORE_OIDC_ISSUER"]
        audience = os.environ.get("CORE_MCP_AUDIENCE", "geostudio-mcp")
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
            )
        except jwt.PyJWTError:
            return None

        return AccessToken(
            token=token,
            client_id=claims.get("azp", "unknown"),
            scopes=claims.get("scope", "").split() if claims.get("scope") else [],
            expires_at=claims.get("exp"),
            resource=audience,
            subject=claims["sub"],
            claims=claims,
        )


class MockTokenVerifier(TokenVerifier):
    """Dev/CI verifier: never contacts Keycloak, always resolves the same
    fixed identity — mirrors get_current_user's CORE_AUTH_MODE=mock branch
    (same mock-sub/mockuser convention)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return AccessToken(
            token=token,
            client_id="mock-client",
            scopes=[],
            expires_at=None,
            resource=os.environ.get("CORE_MCP_AUDIENCE", "geostudio-mcp"),
            subject="mock-sub",
            claims={
                "sub": "mock-sub",
                "preferred_username": "mockuser",
                "given_name": "Mock",
                "family_name": "User",
            },
        )


def get_token_verifier() -> TokenVerifier:
    if os.environ.get("CORE_AUTH_MODE", "oidc") == "mock":
        return MockTokenVerifier()
    return KeycloakTokenVerifier()
```

Note: check the exact import path `mcp.server.auth.provider` against the installed `mcp` package version (`python3 -c "from mcp.server.auth.provider import AccessToken, TokenVerifier"`) — SDK internals can shift between versions; if this import fails, search the installed package (`python3 -c "import mcp.server.auth.provider as m; print(dir(m))"` or `python3 -c "import mcp; print(mcp.__file__)"` then browse the installed source) for the correct current location of `AccessToken`/`TokenVerifier` and adjust the import, keeping the class/method shapes otherwise identical.

- [ ] **Step 5: Install pytest-anyio (or confirm pytest-asyncio) support for async tests**

Check `core/pyproject.toml`'s `dev` dependency group — if there's no async test runner configured yet, add one:
```toml
    "anyio>=4.0",
```
(the `mcp` SDK itself depends on `anyio`, so this likely just needs pytest's anyio plugin enabled — check `python3 -c "import anyio; print(anyio.__version__)"` after `uv sync`; if `pytest.mark.anyio` isn't recognized, add `pytest-anyio` or use `pytest-asyncio` with `@pytest.mark.asyncio` instead, matching whichever is already resolvable from the `mcp` dependency tree — prefer not adding a redundant second async test plugin if one is already pulled in transitively.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_auth.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 7: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS. `app.mcp` needs adding to the layered-architecture contract in `pyproject.toml` as the new top layer (below `app.main`, above `app.public`) — add it now even though Task 3 is what actually populates `app/mcp/routes.py`:
```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.configs",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

- [ ] **Step 8: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/app/mcp core/tests/test_mcp_auth.py
git commit -m "feat(core): TokenVerifier implementations for the MCP endpoint (Keycloak + mock)"
```

---

### Task 3: Mount `/mcp`, add the `whoami` tool, wire the combined lifespan

**Files:**
- Create: `core/app/mcp/server.py`
- Modify: `core/app/main.py`
- Create: `core/tests/test_mcp_routes.py`

**Interfaces:**
- Consumes: `app.mcp.auth.get_token_verifier`, `app.tenants.repository.get_or_create_default_tenant`, `app.users.repository.get_or_create_user`.
- Produces: `app.mcp.server.create_mcp_app() -> Starlette` (the SDK's `streamable_http_app()`, pre-configured with auth), mounted at `/mcp` in `create_app()`.

- [ ] **Step 1: Write the failing tests**

`core/tests/test_mcp_routes.py`:
```python
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
```

Note: the MCP protocol's real request/response shape (initialize handshake, streamable-http session headers) is more involved than a bare `GET` — if `test_mcp_endpoint_exists_and_requires_a_session`'s exact assertion doesn't fit how `streamable_http_app()` actually responds to an unadorned `GET /mcp` (e.g. it might correctly return `406 Not Acceptable` for a request missing the required `Accept: text/event-stream` header, or a `401` if auth is checked before protocol negotiation), adjust the test to assert whatever the SDK's real, correct behavior is — the point of this test is "the route is mounted and reachable," not asserting a specific status code guessed in advance. Verify by running against the actual mounted app and reading the real response before locking in the assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_routes.py -v`
Expected: FAIL — `/mcp` doesn't exist yet (404s), `/.well-known/oauth-protected-resource/mcp` doesn't exist yet.

- [ ] **Step 3: Write `app/mcp/server.py`**

```python
import os

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from sqlalchemy.orm import Session

from app.db import get_session, request_scoped_session
from app.mcp.auth import get_token_verifier
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_mcp: MCPServer | None = None


def create_mcp_server(base_url: str, session_factory) -> MCPServer:
    """base_url is the cœur's own externally-reachable URL, e.g.
    http://localhost:8200 — used to build the /mcp resource identifier and
    (indirectly, via AuthSettings) the RFC 9728 metadata document."""
    server = MCPServer(
        "GeoStudio",
        instructions="GeoStudio cœur MCP endpoint (SP-2a: auth only, no business tools yet).",
        token_verifier=get_token_verifier(),
        auth=AuthSettings(
            issuer_url=os.environ["CORE_OIDC_ISSUER"],
            required_scopes=[],
            resource_server_url=f"{base_url}/mcp",
        ),
    )

    @server.tool()
    async def whoami(ctx: Context) -> dict:
        """Return the identity of the currently authenticated MCP caller —
        proves the OAuth handshake resolves to the same User the shell's
        REST API would resolve for the same Keycloak subject. No real
        business capability; SP-2b adds those."""
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
        claims = access_token.claims

        with request_scoped_session(session_factory) as session:
            tenant = get_or_create_default_tenant(session)
            user = get_or_create_user(
                session,
                tenant_id=tenant.id,
                oidc_sub=access_token.subject,
                username=claims.get("preferred_username", access_token.subject),
                email=claims.get("email"),
                first_name=claims.get("given_name", ""),
                last_name=claims.get("family_name", ""),
            )
            return {"username": user.username, "tenantId": user.tenant_id}

    return server


def get_mcp_server(base_url: str, session_factory) -> MCPServer:
    global _mcp
    if _mcp is None:
        _mcp = create_mcp_server(base_url, session_factory)
    return _mcp
```

Note: confirm the exact import paths (`mcp.server.mcpserver.MCPServer` vs. `mcp.server.fastmcp.FastMCP` — the SDK renamed `FastMCP`→`MCPServer` between major versions; `mcp.server.auth.middleware.auth_context.get_access_token`) against the actually-installed `mcp` version once `uv sync` has run — adjust names if the installed version differs from what's shown here, keeping the same shape (a `TokenVerifier`-backed server, a `Context`-injected tool, `get_access_token()` returning the verified `AccessToken`).

- [ ] **Step 4: Wire into `app/main.py`**

Read the current `create_app()` in full first (it doesn't have an explicit `lifespan=` parameter today). Add the MCP mount and a combined lifespan:

```python
import contextlib
# ... existing imports ...
from app.mcp.server import get_mcp_server


def create_app() -> FastAPI:
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    mcp_server = get_mcp_server(base_url, session_factory)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)

    def get_session_dep() -> Iterator[Session]:
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session_dep

    app.include_router(configs_routes.router)
    app.include_router(items_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(sharing_routes.router)
    app.include_router(public_routes.router)

    app.mount("/mcp", mcp_server.streamable_http_app())

    # ... existing S3ThumbnailStore wiring, /health route ...

    return app
```
Adapt this to the file's actual current structure (variable names, existing route registrations) rather than replacing wholesale — this shows the NEW pieces (`base_url`, `mcp_server`, `lifespan`, the `app.mount("/mcp", ...)` call) to add around the existing ones, which stay as they are.

Add `CORE_BASE_URL` to `.env.example` (default matches the compose stack's exposed port):
```
CORE_BASE_URL=http://localhost:8200
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_routes.py -v`
Expected: PASS (after adjusting the exact status-code assertion per Step 1's note, based on what the real mounted app returns).

- [ ] **Step 6: HTTP-level auth boundary test in `oidc` mode**

Mock mode's `MockTokenVerifier` always succeeds regardless of the
`Authorization` header (Task 2, by design) — the real rejection boundary
only exists in `oidc` mode, so this test builds its own app instance with
`CORE_AUTH_MODE=oidc` rather than reusing the mock-mode `client` fixture,
mirroring `test_auth.py`'s `test_oidc_mode_rejects_wrong_audience` shape:

```python
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
```

Run this once against the real mounted app before finalizing the exact
assertions — if the actual status code or header name differs from what's
shown here (SDK behavior can vary by version), update the assertions to
match what you actually observe, but do not weaken them to something that
would also pass if `/mcp` had no auth enforcement at all (e.g. don't loosen
this to just `response.status_code != 200`).

- [ ] **Step 7: Run the full suite and import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/mcp/server.py core/app/main.py core/tests/test_mcp_routes.py .env.example
git commit -m "feat(core): mount authenticated /mcp with a whoami tool (SP-2a)"
```

---

### Task 4: Compose wiring, manual verification doc

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `CORE_MCP_AUDIENCE`, `CORE_BASE_URL` (Task 2/3's new env vars).
- Produces: the `core` service in `docker-compose.yml` carries the new env vars; a documented manual verification procedure for a real MCP client's OAuth+DCR flow.

- [ ] **Step 1: Add the new env vars to `docker-compose.yml`'s `core` service**

In `docker-compose.yml`'s `core.environment` block, add:
```yaml
      CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
```

- [ ] **Step 2: Add to `.env.example`**

```
CORE_MCP_AUDIENCE=geostudio-mcp
CORE_BASE_URL=http://localhost:8200
```

- [ ] **Step 3: Add the manual verification section to `README.md`**

After the existing "Vérifier le mode `oidc` réel (manuel)" section (added in SP-1d.2), add:

```markdown
### Vérifier le serveur MCP (manuel)

Le serveur MCP (`/mcp`) n'a, à ce stade (SP-2a), aucun outil métier réel —
juste `whoami`, qui prouve que l'authentification OAuth aboutit à la même
identité que l'API REST du shell. Vérification manuelle :

1. `docker compose up -d` (stack complète, `CORE_AUTH_MODE=oidc`, realm
   `geostudio` importé).
2. Avec un client MCP conforme à la spec *MCP Authorization* (ou
   l'inspecteur MCP en ligne de commande), se connecter à
   `http://localhost:8200/mcp`.
3. Le client découvre `/.well-known/oauth-protected-resource/mcp`,
   s'enregistre dynamiquement auprès de Keycloak (DCR), puis déclenche un
   flow OAuth 2.1 + PKCE dans le navigateur — se connecter avec un des
   utilisateurs de démo du realm (`alice`/`Demo1234!`).
4. Une fois connecté, appeler l'outil `whoami` : la réponse doit contenir
   `{"username": "alice", ...}` — la même identité que celle que `GET /me`
   retournerait pour le même utilisateur côté API REST.

Un échec à l'étape 3 avec une erreur de policy `Trusted Hosts` indique que
le realm importé n'a pas la politique de dev de ce plan (Task 1) — vérifier
`deploy/keycloak/geostudio-realm.json`. Un `401` à l'étape 4 indique un
décalage entre `CORE_MCP_AUDIENCE` et l'audience réellement émise par le
realm (vérifier que `geostudio-mcp-audience` est bien un scope par défaut
du realm : `GET /admin/realms/geostudio/default-default-client-scopes`).
```

- [ ] **Step 4: Full stack smoke test**

Run:
```bash
docker compose up -d
docker compose ps
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm test
docker compose down
```
Expected: all green, no regression in the shell (this plan touches no shell code).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example README.md
git commit -m "docs: document manual MCP verification; wire CORE_MCP_AUDIENCE/CORE_BASE_URL into compose"
```
