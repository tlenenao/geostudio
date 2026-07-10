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
