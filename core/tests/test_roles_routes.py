# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role, ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


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
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_catalog_lists_every_privilege_and_requires_admin_roles_manage(env):
    app, client, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/v1/roles/catalog").status_code == 403
    _as(app, admin)
    body = client.get("/v1/roles/catalog").json()
    assert len(body) == len(list(Privilege))
    assert {"privilege", "domain", "labelKey"} <= set(body[0])


def test_list_roles_includes_the_four_built_in(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    body = client.get("/v1/roles").json()
    assert {r["slug"] for r in body} == {"admin", "creator", "analyst", "reader"}
    assert all(r["isBuiltIn"] for r in body)


def test_create_edit_delete_a_custom_role(env):
    app, client, admin, _regular, _roles = env
    _as(app, admin)
    created = client.post(
        "/v1/roles", json={"name": "Support moissonnage", "privileges": ["admin.harvest.manage"]}
    ).json()
    assert created["isBuiltIn"] is False

    patched = client.patch(
        f"/v1/roles/{created['id']}",
        json={"privileges": ["admin.harvest.manage", "admin.collections.manage"]},
    ).json()
    assert len(patched["privileges"]) == 2

    assert client.delete(f"/v1/roles/{created['id']}").status_code == 204
    assert created["id"] not in {r["id"] for r in client.get("/v1/roles").json()}


def test_a_built_in_role_cannot_be_edited_or_deleted(env):
    app, client, admin, _regular, roles = env
    _as(app, admin)
    assert client.patch(f"/v1/roles/{roles['reader']}", json={"name": "x"}).status_code == 400
    assert client.delete(f"/v1/roles/{roles['admin']}").status_code == 400


def test_a_built_in_role_privileges_cannot_be_edited_either(env):
    # Complément du test ci-dessus : l'immuabilité des rôles prédéfinis porte
    # aussi bien sur le nom que sur les privilèges — aucun PATCH ne doit
    # jamais atteindre update_role() pour un rôle is_built_in.
    app, client, admin, _regular, roles = env
    _as(app, admin)
    resp = client.patch(f"/v1/roles/{roles['reader']}", json={"privileges": ["catalog.manage"]})
    assert resp.status_code == 400


def test_deleting_a_role_still_in_use_is_blocked(env):
    # delete_role_route vérifie is_built_in AVANT le nombre de détenteurs —
    # un rôle prédéfini renvoie donc toujours 400 sans jamais exercer le
    # garde `holders > 0` (celui qui évite une violation de contrainte NOT
    # NULL sur users.role_id). Utiliser un rôle personnalisé pour exercer
    # réellement ce garde et vérifier son code 409.
    app, client, admin, regular, _roles = env
    _as(app, admin)
    created = client.post(
        "/v1/roles", json={"name": "Support terrain", "privileges": ["data.view"]}
    ).json()
    assert (
        client.patch(f"/v1/users/{regular.id}", json={"roleId": created["id"]}).status_code == 200
    )
    assert client.delete(f"/v1/roles/{created['id']}").status_code == 409


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
        "/v1/roles",
        json={
            "name": "Super-admin custom",
            "privileges": ["admin.users.manage", "admin.roles.manage"],
        },
    ).json()

    reassign = client.patch(f"/v1/users/{admin.id}", json={"roleId": created["id"]})
    assert reassign.status_code == 200

    resp = client.patch(f"/v1/roles/{created['id']}", json={"privileges": ["admin.users.manage"]})
    assert resp.status_code == 409


def test_removing_admin_roles_manage_from_a_role_that_never_held_the_pair_is_blocked(env):
    # SP-42 / F-securite-autorisation-07 : patch_role exigeait que le rôle
    # édité porte les DEUX privilèges anti-lockout À LA FOIS avant même
    # d'appeler would_orphan_privilege_holders — un rôle sur mesure ne
    # portant QUE admin.roles.manage pouvait se faire retirer ce privilège
    # sans qu'aucune garde ne s'exerce, même s'il en est le seul porteur
    # restant du tenant. État construit par appel direct au dépôt (comme le
    # scénario équivalent PATCH /users, cf. test_users_admin_routes.py) :
    # aucun rôle du tenant ne porte les deux privilèges à la fois.
    app, client, admin, regular, roles = env
    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        r1 = create_role(s, tenant_id=admin.tenant_id, name="R1", privileges=["admin.users.manage"])
        r2 = create_role(s, tenant_id=admin.tenant_id, name="R2", privileges=["admin.roles.manage"])
        set_user_role(
            s, tenant_id=admin.tenant_id, user_id=admin.id, role_id=r1.id, role_slug=r1.slug
        )
        set_user_role(
            s, tenant_id=admin.tenant_id, user_id=regular.id, role_id=r2.id, role_slug=r2.slug
        )
        s.commit()

    _as(app, admin)
    resp = client.patch(f"/v1/roles/{r2.id}", json={"privileges": []})
    assert resp.status_code == 409, resp.text


def test_moving_the_sole_conjoint_holder_off_a_custom_role_is_blocked(env):
    # Scénario nommé par le plan (Task 17) comme jamais testé conjointement :
    # un rôle sur mesure porte À LA FOIS admin.users.manage ET
    # admin.roles.manage, son seul détenteur tente de PATCH /users/{id} pour
    # en changer de rôle lui-même (pas le rôle qu'on édite, l'utilisateur
    # lui-même) — count_users_with_privileges doit bloquer ce PATCH /users
    # exactement comme il bloque déjà le PATCH /roles équivalent.
    app, client, admin, _regular, roles = env
    _as(app, admin)
    created = client.post(
        "/v1/roles",
        json={
            "name": "Super-admin custom",
            "privileges": ["admin.users.manage", "admin.roles.manage"],
        },
    ).json()
    assert client.patch(f"/v1/users/{admin.id}", json={"roleId": created["id"]}).status_code == 200

    resp = client.patch(f"/v1/users/{admin.id}", json={"roleId": roles["reader"]})
    assert resp.status_code == 409
