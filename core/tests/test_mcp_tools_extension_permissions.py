# SPDX-License-Identifier: Apache-2.0
import pytest

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.extensions import repository as ext_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    # Same rationale as test_mcp_tools_configs.py's app_client: the MCP tools
    # close over create_app()'s own engine, so the fixture and the app must
    # share the same on-disk sqlite file rather than two disconnected
    # ":memory:" databases.
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
            username="mockuser", email=None, first_name="Mock", last_name="User",
        )
        # Same pattern as tests/test_configs_extension_permissions.py's
        # `client` fixture: a widget-of-type-extension with a dataSource prop
        # scoped to a single collection ("communes").
        ext_repo.create_extension(
            setup_session, tenant_id=tenant.id, owner_id=mock_user.id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge", module_url="https://x/gauge.js",
            props=[{"name": "source", "type": "dataSource", "label": "Source", "default": None}],
            events=None, actions=None,
            default_size={"w": 2, "h": 2},
            permissions={"collections": ["communes"]},
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    from fastapi.testclient import TestClient
    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.mock_user = mock_user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _config_body(data_source_layer: str) -> dict:
    return {
        "kind": "app",
        "dataSources": [
            {"id": "ds1", "type": "features", "service": "core", "layer": data_source_layer, "query": {}}
        ],
        "layout": {"type": "grid", "items": [
            {"widget": "acme.gauge", "x": 0, "y": 0, "w": 2, "h": 2, "props": {"source": "ds1"}},
        ]},
    }


def test_create_item_rejects_extension_prop_outside_scope(app_client):
    # Mirrors tests/test_configs_extension_permissions.py's
    # test_create_config_rejects_extension_prop_outside_scope, but through
    # the MCP create_item tool rather than POST /configs — proves the same
    # server-side scope guard applies to the MCP write path, not just REST.
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_item",
            {"kind": "app", "title": "My App", "config": _config_body("incidents")},
        )

    assert "acme.gauge" in error_text

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.items.models import Item
        # The rejected create_item must not leave an orphan item behind,
        # mirroring test_rejected_create_does_not_leave_an_orphan_item.
        assert session.scalars(select(Item)).all() == []


def test_create_item_accepts_extension_prop_inside_scope(app_client):
    with app_client:
        result = call_tool(
            app_client, "create_item",
            {"kind": "app", "title": "My App", "config": _config_body("communes")},
        )

    assert result["title"] == "My App"


def test_save_app_config_rejects_extension_prop_outside_scope(app_client):
    with app_client:
        created = call_tool(
            app_client, "create_item",
            {"kind": "app", "title": "My App", "config": _config_body("communes")},
        )
        error_text = call_tool_expecting_error(
            app_client, "save_app_config",
            {"itemId": created["pk"], "config": _config_body("incidents")},
        )

    assert "acme.gauge" in error_text
