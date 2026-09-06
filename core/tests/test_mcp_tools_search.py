# SPDX-License-Identifier: Apache-2.0
"""search_catalog (SP-7 Task 8) — mince adaptateur au-dessus de
items_repo.list_items, même patron de test que test_mcp_tools_create.py."""

from tests.test_mcp_tools_create import (  # noqa: F401 (fixtures/helpers réutilisés)
    app_client,
    call_tool,
    call_tool_raw,
)


def test_search_catalog_returns_items_matching_q(app_client):  # noqa: F811
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


def test_search_catalog_respects_scope(app_client):  # noqa: F811
    with app_client:
        result = call_tool(app_client, "search_catalog", {"scope": "mine"})
    assert result["items"] == []  # aucun item créé par le caller dans ce test


def test_search_collections_returns_collections_matching_q(app_client):  # noqa: F811
    """GAP-40/47 : search_catalog exclut délibérément les collections
    (docstring "items only, not collections") — search_collections est la
    jumelle dédiée, calquée directement sur list_visible_collections (même
    fonction que GET /collections?q=)."""
    from app.collections import repository as collections_repo

    with app_client.session_factory() as session:
        collections_repo.create_collection(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            table_name="communes",
            title="Communes",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        collections_repo.create_collection(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            table_name="ventes",
            title="Ventes",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        session.commit()

    with app_client:
        # search_collections est le premier tool MCP de ce dépôt à retourner
        # une liste nue (list[CollectionSearchResult]) plutôt qu'un objet
        # unique — call_tool()/json.loads(content[0].text) (patron des
        # autres tests de ce fichier) ne convient pas ici : vérifié
        # empiriquement, FastMCP sérialise content[0].text comme l'élément
        # UNIQUE quand un seul résultat matche, pas comme un tableau JSON à
        # un élément — structuredContent["result"] est la forme fiable pour
        # un tool qui retourne une liste, quel que soit son nombre
        # d'éléments (piège CLAUDE.md n°3, vérifié contre le comportement
        # réel, pas supposé).
        raw = call_tool_raw(app_client, "search_collections", {"q": "commune"})

    assert not raw.get("isError")
    result = raw["structuredContent"]["result"]
    assert [c["title"] for c in result] == ["Communes"]
