# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_export_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_export_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_EXPORT_ENABLED", raising=False)
    assert is_export_enabled() is False


def test_is_export_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    assert is_export_enabled() is True
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    assert is_export_enabled() is False


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_reports_export_disabled_by_default(env):
    response = env.get("/v1/instance")
    assert response.status_code == 200
    assert response.json() == {
        "readOnly": False,
        "etlEnabled": False,
        "exportEnabled": False,
        "appExportEnabled": False,
        "tileset3dEnabled": False,
        "terrain3dEnabled": False,
        "copilotEnabled": False,
        "adminToolsEnabled": False,
        "quotasEnabled": False,
    }


def test_instance_reports_export_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    response = env.get("/v1/instance")
    assert response.status_code == 200
    assert response.json()["exportEnabled"] is True
