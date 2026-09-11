# SPDX-License-Identifier: Apache-2.0
"""Compose tous les tools MCP par domaine (SP-43 Étape 8) — remplace le
fichier plat app/mcp/tools.py (1135 lignes, 21 tools) par un paquet d'un
module par domaine, chacun exportant `register(server, session_factory)`.
`from app.mcp.tools import register_tools` (le seul symbole consommé par
app/mcp/server.py) continue de fonctionner sans changement côté appelant —
package au lieu de module, même point d'entrée."""

from mcp.server.fastmcp import FastMCP

from app.configs.schemas import app_config_json_schema
from app.mcp.tools import (
    alerts,
    analytics,
    attachments,
    bookmark,
    catalog,
    configs,
    dataset,
    identity,
    pipelines,
    reports,
    sharing,
)
from app.mcp.tools.write_tools import WRITE_TOOL_NAMES

# REV-008 : READ_ONLY_TOOLS n'est plus un ensemble littéral écrit à la main
# (qui pouvait dériver du code réel, cf. app/mcp/tools/write_tools.py) — même
# objet mutable que WRITE_TOOL_NAMES, peuplé par le décorateur `@write_tool`
# posé sur chaque tool d'écriture, à son point de définition.
READ_ONLY_TOOLS = WRITE_TOOL_NAMES


def register_tools(server: FastMCP, session_factory) -> None:
    for module in (
        identity,
        catalog,
        configs,
        dataset,
        bookmark,
        analytics,
        pipelines,
        alerts,
        reports,
        sharing,
        attachments,
    ):
        module.register(server, session_factory)

    @server.resource("schema://app-config")
    def app_config_schema() -> dict:
        """JSON Schema for AppConfig/DashboardConfig — validate before
        calling create_item or save_app_config."""
        return app_config_json_schema()
