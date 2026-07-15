# SPDX-License-Identifier: Apache-2.0
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
