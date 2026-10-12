# SPDX-License-Identifier: Apache-2.0
"""ARC-26 : gabarits déclaratifs du builder, côté cœur (create_item MCP)."""

import json
from pathlib import Path

import pytest

from app.configs.builder_templates import build_config_from_template, template_ids
from app.configs.widget_registry import BUILTIN_WIDGET_TYPES
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)

_SHELL_DATA = Path(__file__).parents[2] / "shell/src/builder/templates.data.json"


def test_copy_is_identical_to_the_shell_catalog():
    core = json.loads(
        (Path(__file__).parents[1] / "app/configs/builder_templates.json").read_text("utf-8")
    )
    assert core == json.loads(_SHELL_DATA.read_text("utf-8"))


@pytest.mark.parametrize("template_id", template_ids())
def test_every_template_passes_the_app_config_schema(template_id):
    config = build_config_from_template(template_id)
    items = [i for p in config.pages for i in p.layout.items] or config.layout.items
    assert items
    assert {i.widget for i in items} <= BUILTIN_WIDGET_TYPES


def test_atlas_template_declares_an_atlas_on_one_of_its_sources():
    config = build_config_from_template("atlas-par-entite")
    atlas = config.printLayout.atlas
    assert atlas.maxPages == 50
    assert atlas.dataSourceId in {d.id for d in config.dataSources}


def test_unknown_template_is_rejected():
    with pytest.raises(ValueError, match="unknown template"):
        build_config_from_template("nope")


def test_create_item_accepts_a_template(app_client):  # noqa: F811
    with app_client:
        result = call_tool(
            app_client,
            "create_item",
            {"kind": "dashboard", "title": "TdB", "template": "tableau-de-bord-territorial"},
        )
    assert result["title"] == "TdB"
    assert result["resourceType"] == "dashboard"


def test_create_item_template_kind_must_match(app_client):  # noqa: F811
    with app_client:
        err = call_tool_expecting_error(
            app_client,
            "create_item",
            {"kind": "app", "title": "X", "template": "tableau-de-bord-territorial"},
        )
    assert "must match" in err


def test_create_item_requires_exactly_one_of_config_or_template(app_client):  # noqa: F811
    with app_client:
        err = call_tool_expecting_error(app_client, "create_item", {"kind": "app", "title": "X"})
    assert "exactly one" in err
