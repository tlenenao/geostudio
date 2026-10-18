# SPDX-License-Identifier: Apache-2.0
"""AUD-105 : chaque outil MCP porte des annotations cohérentes avec le registre
`@write_tool`, et les prompts sont publiés."""

import asyncio

from mcp.server.fastmcp import FastMCP

from app.mcp.tools import register_tools
from app.mcp.tools.write_tools import (
    DESTRUCTIVE_TOOL_NAMES,
    OPEN_WORLD_TOOL_NAMES,
    WRITE_TOOL_NAMES,
)


def _server() -> FastMCP:
    server = FastMCP("annotations")
    register_tools(server, None)
    return server


def test_every_tool_is_annotated_consistently_with_the_write_registry():
    tools = asyncio.run(_server().list_tools())
    assert tools
    for tool in tools:
        ann = tool.annotations
        assert ann is not None, tool.name
        write = tool.name in WRITE_TOOL_NAMES
        assert ann.readOnlyHint is (not write), tool.name
        if write:
            assert ann.destructiveHint is (tool.name in DESTRUCTIVE_TOOL_NAMES), tool.name
        assert ann.openWorldHint is (tool.name in OPEN_WORLD_TOOL_NAMES), tool.name


def test_destructive_and_open_world_names_exist_or_are_optional_tools():
    names = {t.name for t in asyncio.run(_server().list_tools())}
    # Les outils sous capacité (routage, géocodage…) peuvent être absents ; les
    # écritures destructives de base doivent exister.
    assert {"set_sharing", "save_app_config", "update_item"} <= names
    assert DESTRUCTIVE_TOOL_NAMES <= WRITE_TOOL_NAMES | {"delete_secret"}


def test_prompts_and_discovery_tools_are_published():
    server = _server()
    assert {p.name for p in asyncio.run(server.list_prompts())} >= {
        "review_app_config",
        "explain_collection",
    }
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"list_pipeline_ops", "get_config_history"} <= names
