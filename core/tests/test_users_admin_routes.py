# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


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


def test_list_users_requires_admin(env):
    app, client, _, admin, regular = env
    _as(app, regular)
    assert client.get("/users").status_code == 403
    _as(app, admin)
    body = client.get("/users").json()
    assert body["total"] == 2
    assert {u["username"] for u in body["users"]} == {"admin", "regular"}


def test_promote_then_demote(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    r = client.patch(f"/users/{regular.id}", json={"isAdmin": True})
    assert r.status_code == 200 and r.json()["isAdmin"] is True
    r = client.patch(f"/users/{regular.id}", json={"isAdmin": False})
    assert r.status_code == 200 and r.json()["isAdmin"] is False


def test_last_admin_cannot_be_demoted(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.patch(f"/users/{admin.id}", json={"isAdmin": False}).status_code == 409


def test_patch_unknown_user_404_and_non_admin_403(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    assert client.patch("/users/nope", json={"isAdmin": True}).status_code == 404
    _as(app, regular)
    assert client.patch(f"/users/{admin.id}", json={"isAdmin": False}).status_code == 403


def test_promotion_is_audited(env):
    app, client, Session, admin, regular = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"isAdmin": True})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "user.promote" in actions
