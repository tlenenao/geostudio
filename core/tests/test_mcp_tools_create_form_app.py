import pytest

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import app_client, _register_incidents_collection  # noqa: F401

pytestmark = pytest.mark.postgis


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
