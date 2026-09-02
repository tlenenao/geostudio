# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
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
    return app, client, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_catalog_lists_every_privilege_and_requires_admin_roles_manage(env):
    app, client, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/roles/catalog").status_code == 403
    _as(app, admin)
    body = client.get("/roles/catalog").json()
    assert len(body) == len(list(Privilege))
    assert {"privilege", "domain", "labelKey"} <= set(body[0])


def test_list_roles_includes_the_four_built_in(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    body = client.get("/roles").json()
    assert {r["slug"] for r in body} == {"admin", "creator", "analyst", "reader"}
    assert all(r["isBuiltIn"] for r in body)


def test_create_edit_delete_a_custom_role(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    created = client.post(
        "/roles", json={"name": "Support moissonnage", "privileges": ["admin.harvest.manage"]}
    ).json()
    assert created["isBuiltIn"] is False

    patched = client.patch(
        f"/roles/{created['id']}",
        json={"privileges": ["admin.harvest.manage", "admin.collections.manage"]},
    ).json()
    assert len(patched["privileges"]) == 2

    assert client.delete(f"/roles/{created['id']}").status_code == 204
    assert created["id"] not in {r["id"] for r in client.get("/roles").json()}


def test_a_built_in_role_cannot_be_edited_or_deleted(env):
    app, client, admin, _regular, roles = env
    _as(app, admin)
    assert client.patch(f"/roles/{roles['reader']}", json={"name": "x"}).status_code == 400
    assert client.delete(f"/roles/{roles['admin']}").status_code == 400


def test_a_built_in_role_privileges_cannot_be_edited_either(env):
    # Complément du test ci-dessus : l'immuabilité des rôles prédéfinis porte
    # aussi bien sur le nom que sur les privilèges — aucun PATCH ne doit
    # jamais atteindre update_role() pour un rôle is_built_in.
    app, client, admin, _regular, roles = env
    _as(app, admin)
    resp = client.patch(f"/roles/{roles['reader']}", json={"privileges": ["catalog.manage"]})
    assert resp.status_code == 400


def test_deleting_a_role_still_in_use_is_blocked(env):
    app, client, admin, regular, roles = env
    _as(app, admin)
    client.patch(f"/users/{regular.id}", json={"roleId": roles["reader"]})
    assert client.delete(f"/roles/{roles['reader']}").status_code in (400, 409)


def test_removing_admin_roles_manage_from_the_only_holder_is_blocked(env):
    # Le rôle prédéfini Admin est désormais totalement immuable (y compris
    # ses privilèges) : ce garde-fou anti-lockout ne peut donc s'exercer
    # que sur un rôle personnalisé. On construit un rôle custom qui détient
    # les deux privilèges anti-lockout, on y bascule le seul détenteur (le
    # fixture admin, qui quitte alors le rôle prédéfini Admin — 0 détenteur
    # restant sur ce dernier), rendant le rôle custom seul détenteur des
    # deux privilèges, puis on tente de lui en retirer un.
    app, client, admin, _regular, roles = env
    _as(app, admin)
    created = client.post(
        "/roles",
        json={
            "name": "Super-admin custom",
            "privileges": ["admin.users.manage", "admin.roles.manage"],
        },
    ).json()

    reassign = client.patch(f"/users/{admin.id}", json={"roleId": created["id"]})
    assert reassign.status_code == 200

    resp = client.patch(f"/roles/{created['id']}", json={"privileges": ["admin.users.manage"]})
    assert resp.status_code == 409
