# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user

SOURCE_BODY = {
    "type": "stac", "url": "https://stac.example.com/collections",
    "mode": "reference", "enabled": True, "intervalMinutes": 60,
}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        from app.tenants.repository import get_or_create_default_tenant
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="regular",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_create_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/harvest/sources", json=SOURCE_BODY).status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/harvest/sources", json=SOURCE_BODY)
    assert r.status_code == 201
    assert r.json()["type"] == "stac"
    listed = client.get("/harvest/sources").json()["sources"]
    assert [s["url"] for s in listed] == ["https://stac.example.com/collections"]


def test_create_copy_mode_on_supporting_connector_succeeds(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "mode": "copy"}
    assert client.post("/harvest/sources", json=body).status_code == 201


def test_create_copy_mode_on_unknown_type_is_422(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "type": "arcgis-fs"}
    assert client.post("/harvest/sources", json=body).status_code == 422


def test_patch_requires_admin_and_toggles_enabled(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    _as(app, regular)
    assert client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False}).status_code == 403
    _as(app, admin)
    r = client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_get_and_patch_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="oa", username="other-admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.get(f"/harvest/sources/{created['id']}").status_code == 404
    assert client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False}).status_code == 404


def test_delete_source(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    assert client.delete(f"/harvest/sources/{created['id']}").status_code == 204
    assert client.get("/harvest/sources").json()["sources"] == []


def test_run_defers_a_task_and_is_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    deferred = []
    from app.harvest import routes as harvest_routes

    def fake_deferrer():
        def deferrer(source_id, tenant_id):
            deferred.append((source_id, tenant_id))
        return deferrer

    app.dependency_overrides[harvest_routes.get_task_deferrer] = fake_deferrer
    r = client.post(f"/harvest/sources/{created['id']}/run")
    assert r.status_code == 202
    assert deferred == [(created["id"], admin.tenant_id)]

    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "harvest_source.create" in actions
    assert "harvest_source.run" in actions


def test_run_missing_source_is_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/harvest/sources/does-not-exist/run").status_code == 404


def test_mutations_blocked_in_read_only_mode(env, monkeypatch):
    app, client, _, admin, _regular = env
    _as(app, admin)
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    assert client.post("/harvest/sources", json=SOURCE_BODY).status_code == 403
