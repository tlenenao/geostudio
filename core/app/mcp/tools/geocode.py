# SPDX-License-Identifier: Apache-2.0
"""Tool MCP geocode (REV-102) : jumeau de GET /v1/geocode (mêmes bornes, même
fournisseur, même garde d'egress). Lecture seule ; volontairement absent de
l'allowlist du copilote (app/copilot/tools_allowlist.py)."""

import httpx
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import get_geocoder
from app.mcp.tools.identity import McpToolError, http_exception_to_value_error
from app.ratelimit.limiter import RateLimiter


def register(server: FastMCP, session_factory) -> None:
    # Meme budget que le groupe REST « geocode » (le middleware HTTP ne voit
    # que /mcp, pas l'outil) ; compteur par serveur, par appelant.
    limiter = RateLimiter()

    @server.tool()
    async def geocode(ctx: Context, query: str, limit: int = 5) -> dict:
        """Geocode a postal address or place name (3-200 characters) into
        coordinates. Returns {"results": [{"label", "lon", "lat"}]}, at most
        `limit` (1-10) entries. Read-only. REV-102."""
        if not 3 <= len(query) <= 200:
            raise ValueError("query doit contenir entre 3 et 200 caractères")
        if not 1 <= limit <= 10:
            raise ValueError("limit doit être compris entre 1 et 10")
        token = get_access_token()
        if not limiter.allow(token.subject if token else "anon", "geocode"):
            raise McpToolError(429, "Trop de requêtes de géocodage, réessayez dans une minute.")
        try:
            geocoder = get_geocoder()
        except HTTPException as exc:  # HTTPException 503 : désactivé / fournisseur inconnu
            raise http_exception_to_value_error(exc) from exc
        try:
            results = geocoder.search(query, limit)
        except (EgressBlockedError, httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            raise McpToolError(502, "Le service de géocodage est indisponible.") from None
        return {"results": [r.model_dump() for r in results]}
