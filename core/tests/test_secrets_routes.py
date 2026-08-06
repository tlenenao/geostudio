# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

BEARER_BODY = {
    "name": "weather-api",
    "payload": {"kind": "bearer_token", "token": "s3cr3t-token-value"},
}


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
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
    assert client.post("/secrets", json=BEARER_BODY).status_code == 403


def test_list_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.get("/secrets").status_code == 403


def test_delete_requires_admin(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    _as(app, regular)
    assert client.delete(f"/secrets/{created['id']}").status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/secrets", json=BEARER_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "weather-api"
    assert body["kind"] == "bearer_token"
    assert set(body) == {"id", "name", "kind", "createdAt", "updatedAt"}
    listed = client.get("/secrets").json()
    assert [s["name"] for s in listed] == ["weather-api"]


def test_create_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/secrets", json=BEARER_BODY)
    assert "s3cr3t-token-value" not in r.text


def test_list_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/secrets", json=BEARER_BODY)
    r = client.get("/secrets")
    assert "s3cr3t-token-value" not in r.text


def test_create_duplicate_name_conflicts(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/secrets", json=BEARER_BODY)
    r = client.post("/secrets", json=BEARER_BODY)
    assert r.status_code == 409


def test_delete_removes_secret(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    assert client.delete(f"/secrets/{created['id']}").status_code == 204
    assert client.get("/secrets").json() == []


def test_delete_missing_returns_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.delete("/secrets/does-not-exist").status_code == 404


def test_delete_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()

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
    assert client.delete(f"/secrets/{created['id']}").status_code == 404


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    client.delete(f"/secrets/{created['id']}")

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
        payloads = list(s.scalars(select(AuditLog.payload)))
    assert actions == ["secret.create", "secret.delete"]
    assert all("s3cr3t-token-value" not in str(p) for p in payloads)


def test_create_app_fails_fast_without_master_key(monkeypatch):
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    with pytest.raises(KeyError):
        create_app()
