# SPDX-License-Identifier: Apache-2.0
"""search_catalog (SP-7 Task 8) — mince adaptateur au-dessus de
items_repo.list_items, même patron de test que test_mcp_tools_create.py."""

from tests.test_mcp_tools_create import (  # noqa: F401 (fixtures/helpers réutilisés)
    app_client,
    call_tool,
)


def test_search_catalog_returns_items_matching_q(app_client):
    with app_client:
        call_tool(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "Incidents voirie",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )
        call_tool(
            app_client,
            "create_item",
            {
                "kind": "dashboard",
                "title": "Ventes",
                "config": {"kind": "dashboard", "layout": {"type": "grid", "items": []}},
            },
        )
        result = call_tool(app_client, "search_catalog", {"q": "incidents"})

    assert [i["title"] for i in result["items"]] == ["Incidents voirie"]


def test_search_catalog_respects_scope(app_client):
    with app_client:
        result = call_tool(app_client, "search_catalog", {"scope": "mine"})
    assert result["items"] == []  # aucun item créé par le caller dans ce test
