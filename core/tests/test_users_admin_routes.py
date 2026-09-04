# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
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
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        role_ids = {slug: role.id for slug, role in roles.items()}
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_users_requires_admin_users_manage(env):
    app, client, _, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/users").status_code == 403
    _as(app, admin)
    body = client.get("/users").json()
    assert body["total"] == 2
    assert {u["username"] for u in body["users"]} == {"admin", "regular"}


def test_promote_then_demote_via_role_id(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    r = client.patch(f"/users/{regular.id}", json={"roleId": roles["admin"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "admin"
    r = client.patch(f"/users/{regular.id}", json={"roleId": roles["reader"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "reader"


def test_last_admin_cannot_be_demoted(env):
    app, client, _, admin, _regular, roles = env
    _as(app, admin)
    assert client.patch(f"/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 409


def test_patch_unknown_user_404_and_non_admin_403(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    assert client.patch("/users/nope", json={"roleId": roles["admin"]}).status_code == 404
    _as(app, regular)
    assert client.patch(f"/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 403


def test_patch_user_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular, roles = env
    with Session() as s:
        other_tenant = Tenant(
            id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other"
        )
        s.add(other_tenant)
        s.flush()
        outsider = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="sub-outsider",
            username="outsider",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(outsider)

    _as(app, admin)
    assert client.patch(f"/users/{outsider.id}", json={"roleId": roles["admin"]}).status_code == 404
    with Session() as s:
        refetched = s.get(User, outsider.id)
        assert refetched is not None
        assert refetched.role_id == outsider.role_id
        assert refetched.is_admin is False


def test_role_change_is_audited(env):
    app, client, Session, admin, regular, roles = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"roleId": roles["admin"]})
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "user.role_change" in actions


def test_patch_user_rejects_an_unknown_role_id(env):
    app, client, _, admin, regular, _roles = env
    _as(app, admin)
    assert client.patch(f"/users/{regular.id}", json={"roleId": "nope"}).status_code == 400


def test_list_users_filters_by_username(env):
    app, client, Session, admin, regular, _roles = env
    with Session() as s:
        get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="c",
            username="charlie",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()

    _as(app, admin)
    body = client.get("/users?q=reg").json()
    assert body["total"] == 1
    assert {u["username"] for u in body["users"]} == {"regular"}

    body_ci = client.get("/users?q=REG").json()
    assert body_ci["total"] == 1

    body_all = client.get("/users").json()
    assert body_all["total"] == 3
