from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.db import make_engine, make_session_factory, init_db, request_scoped_session


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

    response = client.get("/schemas/app-config")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "BuilderConfig"
    assert "properties" in body
    engine.dispose()
