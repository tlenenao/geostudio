# SPDX-License-Identifier: Apache-2.0
"""Index AST des outils MCP (SP-61, spec §3.2)."""

import pathlib

from scripts.feature_health.mcp_surface import index_mcp_tools

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_index_finds_every_declared_tool():
    tools = index_mcp_tools(REPO)
    assert len(tools) == 27
    assert "query_features" in tools
    assert "search_collections" in tools  # SP-54


def test_index_is_sorted_and_free_of_duplicates():
    tools = index_mcp_tools(REPO)
    assert list(tools) == sorted(set(tools))


def test_index_ignores_the_schema_resource():
    """`@server.resource("schema://app-config")` (mcp/tools/__init__.py) n'est
    pas un outil : la ressource est inventoriée comme surface `autre`."""
    assert "app_config_schema" not in index_mcp_tools(REPO)
