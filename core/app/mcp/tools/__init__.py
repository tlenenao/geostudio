# SPDX-License-Identifier: Apache-2.0
"""Compose tous les tools MCP par domaine (SP-43 Étape 8) — remplace le
fichier plat app/mcp/tools.py (1135 lignes, 21 tools) par un paquet d'un
module par domaine, chacun exportant `register(server, session_factory)`.
`from app.mcp.tools import register_tools` (le seul symbole consommé par
app/mcp/server.py) continue de fonctionner sans changement côté appelant —
package au lieu de module, même point d'entrée."""

from mcp.server.fastmcp import FastMCP

from app.configs.schemas import BuilderConfig
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

READ_ONLY_TOOLS = {
    "save_app_config",
    "create_item",
    "create_form_app",
    "set_sharing",
    "create_dataset",
    "create_bookmark",
    "create_pipeline",
    "run_pipeline",
}


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
        return BuilderConfig.model_json_schema()
