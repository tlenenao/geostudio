# SPDX-License-Identifier: Apache-2.0
"""SP-42, revue du lot de correctifs 1 — 1 Critical : eafb02cc a bien fermé
F-securite-autorisation-01 sur la surface REST (POST/PUT /configs,
PUT /configs/by-item/{id}, app.configs.routes::_require_privilege_for_kind),
mais le même trou restait grand ouvert sur le second sas d'écriture, le MCP
(app/mcp/tools.py) : create_item (docstring "mirrors POST /configs" — faux
tant qu'aucune garde de privilège n'y était appliquée), create_form_app,
create_dataset, create_bookmark, create_pipeline et save_app_config
appelaient tous configs_repo.create_config/update_config directement, sans
jamais consulter le privilège de domaine. Un rôle « Lecteur » (0 privilège)
obtenait donc toujours un item créé via /mcp, exactement le scénario que
eafb02cc prétendait avoir fermé.

Ce fichier prouve que les cinq tools testables sans PostGIS (create_item,
create_dataset, create_bookmark, create_pipeline, save_app_config) exigent
désormais le même privilège que leur miroir REST — via
app.mcp.tools::_require_config_privilege, qui réutilise verbatim
app.configs.routes::_require_privilege_for_kind (même mapping, pas une
seconde table). create_form_app (le 6e site, introspection PostGIS réelle)
est couvert séparément dans test_mcp_tools_create_form_app.py."""

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.roles.repository import ensure_built_in_roles
from app.users.repository import set_user_role
from tests.test_mcp_tools_create import (  # noqa: F401,F811
    app_client,
    call_tool,
    call_tool_expecting_error,
)
from tests.test_mcp_tools_pipeline import app_client as pipeline_app_client  # noqa: F401,F811


def _demote_to_reader(app_client):  # noqa: F811
    """Rétrograde app_client.mock_user (Créateur par défaut, cf.
    get_or_create_user) vers le rôle prédéfini Lecteur (0 privilège),
    directement en base — même idiome que
    test_configs_privilege_guard.py::env."""
    with app_client.session_factory() as session:
        roles = ensure_built_in_roles(session, tenant_id=app_client.tenant.id)
        assert roles["reader"].privileges == []
        set_user_role(
            session,
            tenant_id=app_client.tenant.id,
            user_id=app_client.mock_user.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        session.commit()


def _seed_app_config(app_client, *, owner=None):  # noqa: F811
    """Crée un item+config kind="app" appartenant à owner (par défaut
    mock_user), pour exercer save_app_config (PUT /configs/by-item mirror)."""
    with app_client.session_factory() as session:
        item_owner = owner or app_client.mock_user
        item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=item_owner.id,
            resource_type="app",
            title="Cible",
        )
        configs_repo.create_config(
            session,
            BuilderConfig(
                version=1, kind="app", layout={"type": "grid", "breakpoints": {}, "items": []}
            ),
            item.id,
            tenant_id=app_client.tenant.id,
        )
        session.commit()
        return item.id


def test_reader_without_any_privilege_is_denied_on_create_item(app_client):  # noqa: F811
    # Reproduit exactement le scénario du Critical : Lecteur, 0 privilège,
    # POST /configs-équivalent via /mcp (create_item, kind="app" ->
    # apps.manage).
    _demote_to_reader(app_client)
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )
    assert "apps.manage" in error_text


def test_creator_can_still_create_an_item_via_mcp(app_client):  # noqa: F811
    # Non-régression : le rôle par défaut (Créateur, qui porte apps.manage)
    # continue d'obtenir un item.
    with app_client:
        result = call_tool(
            app_client,
            "create_item",
            {
                "kind": "app",
                "title": "My App",
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )
    assert result["title"] == "My App"


def test_reader_without_any_privilege_is_denied_on_create_dataset(app_client):  # noqa: F811
    with app_client.session_factory() as session:
        from app.collections import repository as collections_repo

        col = collections_repo.create_collection(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.commit()
        collection_id = col.id
    _demote_to_reader(app_client)
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "create_dataset",
            {"title": "x", "source": "collection", "collectionId": collection_id},
        )
    assert "data.manage" in error_text


def test_reader_without_any_privilege_is_denied_on_create_bookmark(app_client):  # noqa: F811
    # Assertion volontairement générique sur "required" plutôt que sur un
    # nom de privilège précis : le mapping bookmark->privilège est corrigé
    # séparément par le point 2 de cette revue (catalog.manage ->
    # analytics.view) — ce test ne doit pas coupler les deux commits.
    app_item_id = _seed_app_config(app_client)
    _demote_to_reader(app_client)
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "create_bookmark",
            {"title": "Ma vue", "appId": app_item_id, "pageId": "p1"},
        )
    assert "required" in error_text


def test_reader_without_any_privilege_is_denied_on_save_app_config(app_client):  # noqa: F811
    # Miroir MCP de test_configs_privilege_guard.py::
    # test_demoted_owner_can_no_longer_update_their_own_app_config, mais sur
    # save_app_config (PUT /configs/by-item/{id}) plutôt que sur la route
    # REST elle-même.
    item_id = _seed_app_config(app_client)
    _demote_to_reader(app_client)
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "save_app_config",
            {
                "itemId": item_id,
                "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
            },
        )
    assert "apps.manage" in error_text


def test_reader_without_any_privilege_is_denied_on_create_pipeline(pipeline_app_client):  # noqa: F811
    test_client = pipeline_app_client(True)
    with test_client.session_factory() as session:
        roles = ensure_built_in_roles(session, tenant_id=test_client.tenant.id)
        set_user_role(
            session,
            tenant_id=test_client.tenant.id,
            user_id=test_client.mock_user.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        session.commit()
    with test_client:
        error_text = call_tool_expecting_error(
            test_client,
            "create_pipeline",
            {
                "title": "x",
                # Un graphe minimal mais structurellement valide (au moins
                # un reader et un writer) : PipelinePayload._validate_graph
                # rejette un graphe vide AVANT même d'atteindre le nouveau
                # garde de privilège, ce qui masquerait le comportement
                # testé ici (même fixture que
                # test_configs_privilege_guard.py::_body("pipeline")).
                "nodes": [
                    {
                        "id": "r1",
                        "kind": "reader",
                        "op": "reader.collection",
                        "params": {"collectionId": "parcs"},
                    },
                    {
                        "id": "w1",
                        "kind": "writer",
                        "op": "writer.dataset",
                        "params": {"collectionId": "parcs", "title": "sortie"},
                    },
                ],
                "edges": [],
            },
        )
    assert "automation.manage" in error_text
