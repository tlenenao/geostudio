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


def test_get_usage_requires_settings_instance_manage_privilege(env):
    app, client, admin, regular = env
    _as(app, regular)
    resp = client.get("/admin/usage")
    assert resp.status_code == 403


def test_get_usage_returns_snapshot_shape_for_privileged_admin(env):
    app, client, admin, _regular = env
    _as(app, admin)
    resp = client.get("/admin/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"itemCount", "collectionCount", "userCount", "storageBytes"}
    # 2 utilisateurs déjà créés par le fixture (admin + regular).
    assert body["userCount"] == 2
    assert body["itemCount"] == 0
    assert body["collectionCount"] == 0
    assert body["storageBytes"] == 0
