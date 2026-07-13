import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

GAUGE_BODY = {
    "id": "acme.gauge", "tag": "gauge-extension-widget", "label": "Jauge (extension)",
    "moduleUrl": "https://example.com/gauge.js",
    "props": [{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}],
    "events": ["changed"], "actions": ["reset"],
    "defaultSize": {"w": 2, "h": 2},
    "permissions": {"collections": "all"},
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


def test_register_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/extensions", json=GAUGE_BODY).status_code == 403


def test_register_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/extensions", json=GAUGE_BODY)
    assert r.status_code == 201
    assert r.json()["id"] == "acme.gauge"
    listed = client.get("/extensions").json()["extensions"]
    assert [e["id"] for e in listed] == ["acme.gauge"]


def test_register_duplicate_same_tenant_is_409(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    assert client.post("/extensions", json=GAUGE_BODY).status_code == 409


def test_patch_requires_admin_and_toggles_enabled(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    _as(app, regular)
    assert client.patch("/extensions/acme.gauge", json={"enabled": False}).status_code == 403
    _as(app, admin)
    assert client.patch("/extensions/acme.gauge", json={"enabled": False}).status_code == 200
    assert client.get("/extensions").json()["extensions"] == []


def test_get_extensions_is_anonymous_and_scoped_to_default_tenant(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    del app.dependency_overrides[get_current_user_optional]
    listed = client.get("/extensions").json()["extensions"]
    assert [e["id"] for e in listed] == ["acme.gauge"]


def test_get_extensions_never_leaks_across_tenants(env):
    app, client, Session, admin, _regular = env
    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="oa", username="other-admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    _as(app, other_admin)
    assert client.get("/extensions").json()["extensions"] == []


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "extension.create" in actions
    assert "extension.update" in actions
