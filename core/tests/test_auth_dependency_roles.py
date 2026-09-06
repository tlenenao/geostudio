# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import list_roles
from app.tenants.repository import get_or_create_default_tenant


def test_a_fresh_tenant_gets_its_four_built_in_roles_on_first_authenticated_call(monkeypatch):
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

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        assert list_roles(s, tenant_id=tenant.id) == []

    assert client.get("/v1/me", headers={"Authorization": "Bearer test-token"}).status_code == 200

    with Session() as s:
        slugs = {r.slug for r in list_roles(s, tenant_id=tenant.id)}
    assert slugs == {"admin", "creator", "analyst", "reader"}
