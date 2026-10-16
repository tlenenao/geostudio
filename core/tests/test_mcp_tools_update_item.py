# SPDX-License-Identifier: Apache-2.0
"""REV-367 h : tool MCP `update_item` (métadonnées, contentStatus, catégories)
avec garde de version `expectedUpdatedAt` (équivalent MCP de If-Match)."""

from tests import test_mcp_tools_sharing as _base

_seed_item = _base._seed_item
call_tool = _base.call_tool
call_tool_expecting_error = _base.call_tool_expecting_error
app_client = _base.app_client  # fixture réutilisée telle quelle


def test_update_item_sets_metadata_status_and_categories(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    with app_client:
        result = call_tool(
            app_client,
            "update_item",
            {
                "itemId": item_id,
                "title": "Nouveau titre",
                "keywords": ["a", "b"],
                "contentStatus": "authoritative",
                "categories": ["cat-1"],
            },
        )
    assert result["title"] == "Nouveau titre"
    assert result["keywords"] == ["a", "b"]
    assert result["contentStatus"] == "authoritative"
    assert result["categories"] == ["cat-1"]


def test_update_item_refuses_a_stale_expected_updated_at(app_client):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    with app_client:
        first = call_tool(app_client, "update_item", {"itemId": item_id, "title": "v1"})
        error = call_tool_expecting_error(
            app_client,
            "update_item",
            {"itemId": item_id, "title": "v2", "expectedUpdatedAt": "2000-01-01T00:00:00"},
        )
        assert "stale" in error.lower() or "412" in error
        # La version lue juste avant passe.
        ok = call_tool(
            app_client,
            "update_item",
            {"itemId": item_id, "title": "v3", "expectedUpdatedAt": first["updatedAt"]},
        )
    assert ok["title"] == "v3"


def test_update_item_on_an_unknown_item_errors(app_client):
    with app_client:
        error = call_tool_expecting_error(
            app_client, "update_item", {"itemId": "nope", "title": "x"}
        )
    assert "not found" in error.lower()
