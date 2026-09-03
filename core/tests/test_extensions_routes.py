# SPDX-License-Identifier: Apache-2.0
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
    "id": "acme.gauge",
    "tag": "gauge-extension-widget",
    "label": "Jauge (extension)",
    "moduleUrl": "https://example.com/gauge.js",
    "props": [{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}],
    "events": ["changed"],
    "actions": ["reset"],
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
            s,
            tenant_id=other_tenant.id,
            oidc_sub="oa",
            username="other-admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    _as(app, other_admin)
    assert client.get("/extensions").json()["extensions"] == []


def test_patch_extension_cross_tenant_returns_404(env):
    # repo.get_extension filters by (tenant_id, id) — an admin of a DIFFERENT
    # tenant must not be able to disable/alter an extension registered under
    # another tenant just by guessing its id. test_get_extensions_never_leaks_
    # across_tenants already covers GET; PATCH had no equivalent before this
    # review (brief explicitly calls out extensions as a module requiring
    # cross-tenant coverage, SP-8c).
    app, client, Session, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other-patch", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="oa-patch",
            username="other-admin-patch",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.patch("/extensions/acme.gauge", json={"enabled": False}).status_code == 404

    _as(app, admin)
    assert client.get("/extensions").json()["extensions"][0]["enabled"] is True


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "extension.create" in actions
    assert "extension.update" in actions


def test_get_extensions_all_true_shows_disabled_to_admin(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    default_listed = client.get("/extensions").json()["extensions"]
    assert default_listed == []
    all_listed = client.get("/extensions?all=true").json()["extensions"]
    assert [e["id"] for e in all_listed] == ["acme.gauge"]


def test_get_extensions_all_true_ignored_for_non_admin(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    _as(app, regular)
    listed = client.get("/extensions?all=true").json()["extensions"]
    assert listed == []


def test_get_extensions_all_true_ignored_for_anonymous(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})
    del app.dependency_overrides[get_current_user_optional]
    listed = client.get("/extensions?all=true").json()["extensions"]
    assert listed == []


def test_get_extensions_all_true_shown_to_custom_role_with_extensions_manage(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, Session, admin, regular = env
    _as(app, admin)
    client.post("/extensions", json=GAUGE_BODY)
    client.patch("/extensions/acme.gauge", json={"enabled": False})

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire d'extensions",
            privileges=[Privilege.ADMIN_EXTENSIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)
        all_listed = client.get("/extensions?all=true").json()["extensions"]
        assert [e["id"] for e in all_listed] == ["acme.gauge"]
