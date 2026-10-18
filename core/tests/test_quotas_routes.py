# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.quotas import routes as quotas_routes
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):  # noqa: N803
        return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[quotas_routes.get_s3_client] = lambda: _FakeS3Client()
    client = TestClient(app)
    return app, client, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def _grant_quotas_privilege(app, user) -> None:
    from app.roles.models import Role
    from app.roles.privileges import Privilege
    from app.roles.repository import update_role

    session = next(app.dependency_overrides[db.get_session]())
    role = session.get(Role, user.role_id)
    update_role(
        session,
        tenant_id=user.tenant_id,
        role_id=role.id,
        name=None,
        privileges=[*role.privileges, Privilege.ADMIN_QUOTAS_MANAGE.value],
    )
    session.commit()
    session.close()


def test_put_tenant_limits_requires_dedicated_privilege_then_overrides_instance_limits(env):
    app, client, admin, _regular = env
    _as(app, admin)
    body = {"maxItems": 5, "maxUsers": 9}
    assert client.put("/v1/admin/usage/limits", json=body).status_code == 403
    _grant_quotas_privilege(app, admin)
    resp = client.put("/v1/admin/usage/limits", json=body)
    assert resp.status_code == 200
    usage = client.get("/v1/admin/usage").json()
    assert (usage["maxItems"], usage["maxUsers"], usage["maxCollections"]) == (5, 9, None)
    # PUT complet : remettre à null retombe sur la limite d'instance.
    assert client.put("/v1/admin/usage/limits", json={}).status_code == 200
    assert client.get("/v1/admin/usage").json()["maxItems"] is None
    assert client.put("/v1/admin/usage/limits", json={"maxItems": -1}).status_code == 422


def test_get_usage_requires_settings_instance_manage_privilege(env):
    app, client, admin, regular = env
    _as(app, regular)
    resp = client.get("/v1/admin/usage")
    assert resp.status_code == 403


def test_get_usage_returns_snapshot_shape_for_privileged_admin(env):
    app, client, admin, _regular = env
    _as(app, admin)
    resp = client.get("/v1/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "itemCount",
        "collectionCount",
        "userCount",
        "storageBytes",
        "maxItems",
        "maxCollections",
        "maxStorageBytes",
        "maxUsers",
        "maxActiveRuns",
    }
    # 2 utilisateurs déjà créés par le fixture (admin + regular).
    assert body["userCount"] == 2
    assert body["itemCount"] == 0
    assert body["collectionCount"] == 0
    assert body["storageBytes"] == 0


def test_get_usage_includes_configured_limits(env, monkeypatch):
    app, client, admin, _regular = env
    _as(app, admin)
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "500")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000000")
    monkeypatch.setenv("CORE_QUOTA_MAX_USERS_PER_TENANT", "7")
    monkeypatch.setenv("CORE_QUOTA_MAX_ACTIVE_RUNS_PER_TENANT", "3")
    resp = client.get("/v1/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["maxItems"] == 500
    assert body["maxCollections"] is None
    assert body["maxStorageBytes"] == 1000000
    assert body["maxUsers"] == 7
    assert body["maxActiveRuns"] == 3


def test_get_usage_limits_are_null_when_unconfigured(env):
    app, client, admin, _regular = env
    _as(app, admin)
    resp = client.get("/v1/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["maxItems"] is None
    assert body["maxCollections"] is None
    assert body["maxStorageBytes"] is None
