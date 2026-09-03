# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import db
from app.admin_tools.tokens import mint_launch_token, mint_session_token
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

_SECRET = "test-admin-tools-secret-padding-0123456"


@pytest.fixture(autouse=True)
def admin_tools_env(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as s:
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
        member = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="m",
            username="member",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        s.commit()
        admin_id, member_id = admin.id, member.id

    app = create_app()

    def override_session():
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    def use_as(user_id: str) -> None:
        def _dep():
            with request_scoped_session(session_factory) as session:
                return session.get(User, user_id)

        app.dependency_overrides[get_current_user] = _dep

    return TestClient(app), use_as, admin_id, member_id, session_factory


def test_routes_absent_when_disabled(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "false")
    client = TestClient(create_app())
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 404


def test_launch_requires_admin(env):
    client, use_as, _admin_id, member_id, _sf = env
    use_as(member_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 403


def test_launch_rejects_unknown_tool(env):
    client, use_as, admin_id, _member_id, _sf = env
    use_as(admin_id)
    response = client.post("/admin-tools/launch/not-a-real-tool")
    assert response.status_code == 422


def test_launch_returns_session_url_for_admin(env):
    client, use_as, admin_id, _member_id, _sf = env
    use_as(admin_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 200
    url = response.json()["url"]
    assert url.startswith("http://localhost:8200/admin-tools/session/martin?_at=")


def test_session_redirects_and_sets_cookie_on_valid_token(env):
    client, _use_as, admin_id, _member_id, _sf = env
    token = mint_launch_token(sub=admin_id, tool="martin")
    response = client.get(f"/admin-tools/session/martin?_at={token}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/martin/"
    set_cookie = response.headers["set-cookie"]
    assert "gs_admin_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Path=/admin" in set_cookie


def test_session_rejects_expired_launch_token(env):
    client, _use_as, admin_id, _member_id, _sf = env
    now = int(time.time())
    expired = jwt.encode(
        {
            "typ": "admin_launch",
            "sub": admin_id,
            "tool": "martin",
            "iat": now - 120,
            "exp": now - 60,
        },
        _SECRET,
        algorithm="HS256",
    )
    response = client.get(f"/admin-tools/session/martin?_at={expired}", follow_redirects=False)
    assert response.status_code == 401


def test_session_rejects_tool_mismatch(env):
    client, _use_as, admin_id, _member_id, _sf = env
    token = mint_launch_token(sub=admin_id, tool="martin")
    response = client.get(f"/admin-tools/session/titiler?_at={token}", follow_redirects=False)
    assert response.status_code == 401


def test_verify_accepts_valid_session_cookie(env):
    client, _use_as, admin_id, _member_id, _sf = env
    token = mint_session_token(sub=admin_id)
    client.cookies.set("gs_admin_session", token)
    response = client.get("/admin-tools/verify")
    assert response.status_code == 200


def test_verify_rejects_missing_cookie(env):
    client, _use_as, _admin_id, _member_id, _sf = env
    response = client.get("/admin-tools/verify")
    assert response.status_code == 403


def test_verify_rejects_expired_session_cookie(env):
    client, _use_as, admin_id, _member_id, _sf = env
    now = int(time.time())
    expired = jwt.encode(
        {"typ": "admin_session", "sub": admin_id, "iat": now - 2000, "exp": now - 1},
        _SECRET,
        algorithm="HS256",
    )
    client.cookies.set("gs_admin_session", expired)
    response = client.get("/admin-tools/verify")
    assert response.status_code == 403


def test_launch_allowed_for_custom_role_with_settings_instance_manage(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import set_user_role

    client, use_as, _admin_id, member_id, session_factory = env

    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Infra",
            privileges=[Privilege.SETTINGS_INSTANCE_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=member_id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()

    use_as(member_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 200


def test_launch_rejected_for_custom_role_without_settings_instance_manage(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import set_user_role

    client, use_as, _admin_id, member_id, session_factory = env

    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=member_id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()

    use_as(member_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 403
