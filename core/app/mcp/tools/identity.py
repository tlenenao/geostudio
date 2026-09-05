# SPDX-License-Identifier: Apache-2.0
"""Fondations partagées par tous les tools/<domaine>.py (SP-43 Étape 8) :
résolution de l'identité de l'appelant MCP et une poignée de gardes
d'accès qui n'ont pas de service REST équivalent à réutiliser (les gardes
qui EN ont un vivent dans app.items.service/app.configs.service/
app.pipelines.service à la place). Enregistré en premier par
tools/__init__.py::register_tools — les autres modules importent leurs
helpers d'ici plutôt que de les recopier."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.auth.dependency import admin_subs, analyst_subs
from app.collections import repository as collections_repo
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import ItemAccessFacts, can
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def without_thumbnail_url(item: ItemRead) -> ItemRead:
    """SP-42, correctif 2 (F-coeur-federation-08) : ItemRead.thumbnailUrl
    pointe vers GET /items/{id}/thumbnail, gardée par l'audience OIDC du
    shell (CORE_OIDC_AUDIENCE). Un jeton MCP porte l'audience distincte
    CORE_MCP_AUDIENCE (app/mcp/auth.py) et reçoit systématiquement 401 sur
    cette route — servir cette URL à un agent MCP promettrait un accès qui
    échoue toujours. Plutôt que d'élargir une garde d'authentification (les
    deux options qu'aurait demandé un mécanisme d'échange), on cesse de la
    produire côté MCP ; le champ reste `str | None` côté schéma REST, donc
    ce None ne casse aucun contrat de tool."""
    return item.model_copy(update={"thumbnailUrl": None})


def without_thumbnail_urls(page: ItemPage) -> ItemPage:
    return page.model_copy(update={"items": [without_thumbnail_url(i) for i in page.items]})


def resolve_actor(session, access_token) -> User:
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
        bootstrap_admin=access_token.subject in admin_subs(),
        bootstrap_analyst=access_token.subject in analyst_subs(),
    )


def require_access(session, *, user: User, item_id: str, action: str) -> ItemAccessFacts:
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


def require_collection_read(session, *, user: User, collection_id: str):
    """Mirrors app/collections/routes.py's get_readable_collection — ValueError
    instead of HTTPException, same rationale as require_access above."""
    col = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id
    )
    if col is None:
        raise ValueError("collection not found")
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    readable = can_manage_collections or can(
        session,
        user_id=user.id,
        action="read",
        item=collections_repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        raise ValueError("collection not found")
    return col


def http_exception_to_value_error(exc: HTTPException) -> ValueError:
    """Petit adaptateur commun : tout service partagé avec la route REST
    (app.items.service/app.configs.service/app.pipelines.service) lève
    HTTPException — un tool MCP n'a pas de canal de statut HTTP, donc chaque
    site d'appel la retraduit en ValueError (message identique), même
    patron que les validateurs par kind déjà existants avant SP-43."""
    return ValueError(exc.detail)


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def whoami(ctx: Context) -> dict:
        """Return the identity of the currently authenticated MCP caller —
        proves the OAuth handshake resolves to the same User the shell's
        REST API would resolve for the same Keycloak subject."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            return {"username": user.username, "tenantId": user.tenant_id}
