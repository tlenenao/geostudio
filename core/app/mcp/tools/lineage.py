# SPDX-License-Identifier: Apache-2.0
"""Tool MCP get_item_impact (ARC4-F15) — jumelle de GET /v1/{items|collections}/{id}/impact :
même service (`app.lineage.service`), mêmes règles de visibilité (dépendants illisibles
comptés, jamais nommés). Lecture seule."""

import json

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.db import request_scoped_session
from app.lineage import service
from app.mcp.tools.identity import resolve_actor


def register(server: FastMCP, session_factory) -> None:
    @server.tool(structured_output=False)
    async def get_item_impact(ctx: Context, id: str, type: str = "item") -> str:
        """List what depends on an item (type="item", default) or a collection
        (type="collection") — i.e. what would break if it were deleted: visible
        dependents (transitive, with depth) plus the count of dependents the caller
        cannot read (never named). Returns a JSON object. Read-only."""
        if type not in ("item", "collection"):
            raise ValueError("type must be 'item' or 'collection'")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            graph = service.build_graph(session, tenant_id=user.tenant_id)
            key = (type, id)
            if key not in graph.titles or key not in service.visible_nodes(session, user, {key}):
                raise ValueError(f"{type} '{id}' not found")
            return json.dumps(service.impact(session, user, key, graph=graph))
