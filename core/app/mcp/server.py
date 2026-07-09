import os

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP

from app.db import request_scoped_session
from app.mcp.auth import get_token_verifier
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def create_mcp_server(base_url: str, session_factory) -> FastMCP:
    """base_url is the cœur's own externally-reachable URL, e.g.
    http://localhost:8200 — used to build the /mcp resource identifier and
    (indirectly, via AuthSettings) the RFC 9728 metadata document."""
    server = FastMCP(
        "GeoStudio",
        instructions="GeoStudio cœur MCP endpoint (SP-2a: auth only, no business tools yet).",
        token_verifier=get_token_verifier(),
        auth=AuthSettings(
            issuer_url=os.environ.get(
                "CORE_OIDC_ISSUER", "http://localhost:8180/realms/geostudio"
            ),
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
