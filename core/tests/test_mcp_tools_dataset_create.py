# SPDX-License-Identifier: Apache-2.0
"""create_dataset (SP-14l) — mirrors POST /configs with kind="dataset":
same DatasetPayload construction, same per-source readability validation
(app.configs.dataset_validation) as the REST route. SQLite is enough here —
neither source variant needs real PostGIS introspection at creation time,
only catalog metadata (Collection row / harvested "external" item row)."""
from sqlalchemy import select

from app.audit.models import AuditLog
from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401


def _register_collection(app_client, *, public=True, owner=None):
    with app_client.session_factory() as session:
        col = collections_repo.create_collection(
            session, tenant_id=app_client.tenant.id, owner_id=(owner or app_client.mock_user).id,
            table_name="incidents", title="Incidents", description="", is_public=public,
            pk_column="id", geometry_column="geom", geometry_type="Point", srid=4326,
        )
        session.commit()
        return col.id


def _register_arcgis_layer(app_client, *, public=True, owner=None):
    with app_client.session_factory() as session:
        layer_owner = owner or app_client.mock_user
        source = harvest_repo.create_source(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id,
            resource_type="external", title="Bâtiments",
        )
        if public:
            items_repo.set_is_public(
                session, tenant_id=app_client.tenant.id, item_id=layer_item.id, is_public=True,
            )
        harvest_repo.create_record(
            session, tenant_id=app_client.tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0",
            layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def test_create_dataset_collection_source_creates_item_and_config(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.kind == "dataset"
        assert config.config.dataset.source == "collection"
        assert config.config.dataset.collectionId == collection_id


def test_create_dataset_arcgis_source_creates_item_and_config(app_client):
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.source == "arcgis"
        assert config.config.dataset.arcgisItemId == arcgis_item_id


def test_create_dataset_accepts_columns_time_field_and_reacts_to_extent(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
            "columns": {"titre": {"label": "Titre", "description": None, "format": None}},
            "timeField": "created_at", "reactsToExtent": True,
        })

    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.columns["titre"].label == "Titre"
        assert config.config.dataset.timeField == "created_at"
        assert config.config.dataset.reactsToExtent is True


def test_create_dataset_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    with app_client.session_factory() as session:
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)


def test_create_dataset_unreadable_collection_errors_without_leaking_existence(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd-sub",
            username="otherowner-cd", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        collection_id = _register_collection(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })
    assert "not found" in error_text


def test_create_dataset_unreadable_arcgis_layer_errors(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd2-sub",
            username="otherowner-cd2", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })
    assert "not found" in error_text
