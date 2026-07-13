import pytest
from sqlalchemy import text

from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import app_client, _register_incidents_collection  # noqa: F401

pytestmark = pytest.mark.postgis


def _register_incidents_collection_owned_by_other(app_client):
    """Same table/collection as _register_incidents_collection, but owned by
    a second user distinct from app_client.mock_user, with no
    CollectionShare granting mock_user write access. is_public=True so
    mock_user (CORE_AUTH_MODE=mock always resolves that one fixed identity —
    see app_client's docstring/comment above — there's no way to "switch
    identity" for the MCP call itself) can still read it, exercising the
    read-yes/write-no gap the review finding was about rather than a
    read-denied 404."""
    with app_client.session_factory() as session:
        from app.collections.ddl import apply_collection_ddl
        from app.collections import repository as collections_repo
        tenant = get_or_create_default_tenant(session)
        other_owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="other-owner-sub",
            username="otherowner", email=None, first_name="Other", last_name="Owner",
        )
        session.execute(text(
            "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
            "titre text, geom geometry(Point, 4326))"
        ))
        session.commit()
        apply_collection_ddl(session, "incidents")
        col = collections_repo.create_collection(
            session, tenant_id=tenant.id, owner_id=other_owner.id,
            table_name="incidents", title="Incidents", description="", is_public=True,
            pk_column="id", geometry_column="geom", geometry_type="Point", srid=4326,
        )
        session.execute(text(
            "INSERT INTO incidents (tenant_id, titre, geom) VALUES "
            "(:tid, 'Nid de poule', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
        ), {"tid": tenant.id})
        session.commit()
        return col.id


def test_create_form_app_non_owner_without_write_access_gets_map_table_only(app_client):
    # Closes the review finding on Task 10: can_write_collection was only
    # verified by inspection end-to-end, never exercised returning False
    # through the real create_form_app tool call. mock_user here is neither
    # owner nor shared-in on the collection (see helper above) — they can
    # read it (is_public=True) but must not get a write-capable Formulaire.
    with app_client:
        collection_id = _register_incidents_collection_owned_by_other(app_client)
        result = call_tool(app_client, "create_form_app", {"collectionId": collection_id})

    assert result["resourceType"] == "app"
    with app_client.session_factory() as session:
        from app.configs import repository as configs_repo
        config = configs_repo.get_config_by_item(session, result["pk"])
        widget_types = [item.widget for item in config.config.layout.items]
        assert widget_types == ["map", "table"]
        assert config.config.messages == []


def test_create_form_app_owner_gets_form_map_table(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        result = call_tool(app_client, "create_form_app", {"collectionId": collection_id})

    assert result["resourceType"] == "app"
    with app_client.session_factory() as session:
        from app.configs import repository as configs_repo
        config = configs_repo.get_config_by_item(session, result["pk"])
        widget_types = [item.widget for item in config.config.layout.items]
        assert widget_types == ["form", "map", "table"]


def test_create_form_app_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        call_tool(app_client, "create_form_app", {"collectionId": collection_id})

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows if r.object_type in ("item", "config"))


def test_create_form_app_unknown_collection_errors(app_client):
    with app_client:
        error_text = call_tool_expecting_error(app_client, "create_form_app", {"collectionId": "nope"})
    assert "not found" in error_text
