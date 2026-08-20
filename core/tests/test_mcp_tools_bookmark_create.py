# SPDX-License-Identifier: Apache-2.0
"""create_bookmark (SP-14m) — mirrors POST /configs with kind="bookmark":
same BookmarkPayload construction, same appId readability validation
(app.configs.bookmark_validation) as the REST route."""

from sqlalchemy import select

from app.audit.models import AuditLog
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)


def _register_app(app_client, *, owner=None) -> str:
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


def test_create_bookmark_creates_item_and_config(app_client):
    with app_client:
        app_id = _register_app(app_client)
        result = call_tool(
            app_client,
            "create_bookmark",
            {
                "title": "Ma vue",
                "appId": app_id,
                "pageId": "page-1",
                "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
            },
        )

    assert result["resourceType"] == "bookmark"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.kind == "bookmark"
        assert config.config.bookmark.appId == app_id
        assert config.config.bookmark.pageId == "page-1"
        assert config.config.bookmark.timeRange.from_ == "2026-01-01"


def test_create_bookmark_accepts_extent_and_cross_filter(app_client):
    with app_client:
        app_id = _register_app(app_client)
        result = call_tool(
            app_client,
            "create_bookmark",
            {
                "title": "Ma vue",
                "appId": app_id,
                "pageId": "page-1",
                "extent": [2.0, 46.0, 3.0, 47.0],
                "crossFilter": {
                    "dataset-1": {"field": "region", "value": "Nord", "originSourceId": "src-1"}
                },
            },
        )

    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.bookmark.extent == (2.0, 46.0, 3.0, 47.0)
        assert config.config.bookmark.crossFilter["dataset-1"].field == "region"


def test_create_bookmark_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        app_id = _register_app(app_client)
        call_tool(
            app_client, "create_bookmark", {"title": "Ma vue", "appId": app_id, "pageId": "page-1"}
        )

    with app_client.session_factory() as session:
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)


def test_create_bookmark_unreadable_app_errors_without_leaking_existence(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="other-owner-cb-sub",
            username="otherowner-cb",
            email=None,
            first_name="Other",
            last_name="Owner",
        )
        session.commit()
    with app_client:
        app_id = _register_app(app_client, owner=other_owner)
        error_text = call_tool_expecting_error(
            app_client,
            "create_bookmark",
            {
                "title": "Ma vue",
                "appId": app_id,
                "pageId": "page-1",
            },
        )
    assert "app not found" in error_text


def test_create_bookmark_empty_page_id_errors(app_client):
    with app_client:
        app_id = _register_app(app_client)
        error_text = call_tool_expecting_error(
            app_client,
            "create_bookmark",
            {
                "title": "Ma vue",
                "appId": app_id,
                "pageId": "  ",
            },
        )
    assert error_text  # Pydantic ValidationError surfaced as a tool error
