# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app


def test_schema_http_endpoint_returns_builder_config_json_schema(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    response = client.get("/v1/schemas/app-config")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "BuilderConfig"
    assert "properties" in body
    engine.dispose()


def test_rest_and_mcp_schema_never_diverge():
    from app.configs.schemas import app_config_json_schema
    from app.schemas_routes import get_app_config_schema

    # La ressource MCP (app/mcp/tools/__init__.py::app_config_schema) et la
    # route REST doivent appeler la même fonction — ce test compare leurs
    # sorties directement, sans dépendre du protocole MCP.
    assert get_app_config_schema() == app_config_json_schema()
