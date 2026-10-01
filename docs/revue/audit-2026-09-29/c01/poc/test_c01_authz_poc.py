# SPDX-License-Identifier: Apache-2.0
"""PoC d'audit c01 (2026-09-29) — lecture seule sur le code : ces tests
DÉMONTRENT un comportement actuel (ils passent tant que le défaut existe).
Aucun n'appartient à la suite du dépôt. Rejouer :

    cd core && uv run pytest ../docs/revue/audit-2026-09-29/c01/poc -q -p no:cacheprovider
"""

import os

os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
os.environ.setdefault("CORE_ENV", "development")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.auth.dependency import get_current_user, get_current_user_optional  # noqa: E402
from app.collections import routes as collections_routes  # noqa: E402
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound  # noqa: E402
from app.db import init_db, make_engine, make_session_factory, request_scoped_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.roles.privileges import Privilege  # noqa: E402
from app.roles.repository import create_role, ensure_built_in_roles  # noqa: E402
from app.tenants.repository import get_or_create_default_tenant  # noqa: E402
from app.users.repository import get_or_create_user  # noqa: E402

EMPLOYEES = TableInfo(
    table_name="employees",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="nom", type="string", required=True),
        ColumnInfo(name="salary", type="integer", required=False),
    ],
)


def _introspector(session, table_name):
    if table_name != "employees":
        raise TableNotFound(table_name)
    return EMPLOYEES


@pytest.fixture(autouse=True)
def _share_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "c01-audit-share-link-secret-000000")


def _mk_user(s, tenant_id, sub, **kw):
    return get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
        **kw,
    )


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = _mk_user(s, tenant.id, "owner", bootstrap_admin=True)
        editor = _mk_user(s, tenant.id, "editor")  # rôle par défaut : Créateur
        viewer = _mk_user(s, tenant.id, "viewer")
        um_role = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestion des utilisateurs",
            privileges=[Privilege.ADMIN_USERS_MANAGE.value],
        )
        user_manager = _mk_user(s, tenant.id, "usermgr")
        user_manager.role_id = um_role.id
        user_manager.is_admin = False
        admin_role_id = ensure_built_in_roles(s, tenant_id=tenant.id)["admin"].id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: _introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table, tenant_id=None: None
    )
    client = TestClient(app)
    return {
        "app": app,
        "client": client,
        "owner": owner,
        "editor": editor,
        "viewer": viewer,
        "user_manager": user_manager,
        "admin_role_id": admin_role_id,
        "Session": Session,
    }


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _anonymous(app):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


def _group_with(client, member_id: str) -> str:
    gid = client.post("/v1/groups", json={"name": "equipe"}).json()["id"]
    assert client.post(f"/v1/groups/{gid}/members", json={"userId": member_id}).status_code == 204
    return gid


def _app_item(client, title="App") -> str:
    body = {"kind": "app", "dataSources": [], "layout": {"type": "grid", "items": []}}
    r = client.post("/v1/configs", json={"title": title, "config": body})
    assert r.status_code == 201, r.text
    return r.json()["itemId"]


# --- c01-001 : un éditeur délégué d'une collection lève le masquage GAP-22 ---


def test_collection_editor_without_view_sensitive_can_unmark_sensitive_fields(env):
    app, client, owner, editor = env["app"], env["client"], env["owner"], env["editor"]
    _as(app, owner)
    assert client.post("/v1/collections", json={"tableName": "employees"}).status_code == 201
    r = client.patch("/v1/collections/employees", json={"sensitiveFields": ["salary"]})
    assert r.status_code == 200 and r.json()["sensitiveFields"] == ["salary"]
    gid = _group_with(client, editor.id)
    r = client.put(
        "/v1/collections/employees/sharing",
        json={"public": False, "groups": [{"groupId": gid, "role": "editor"}]},
    )
    assert r.status_code == 200

    _as(app, editor)
    me = client.get("/v1/me").json()
    assert Privilege.DATA_VIEW_SENSITIVE.value not in me["privileges"]
    # Défaut : aucune garde de privilège sur sensitiveFields, seul `write` compte.
    r = client.patch("/v1/collections/employees", json={"sensitiveFields": []})
    assert r.status_code == 200
    assert r.json()["sensitiveFields"] == []


# --- c01-002 : admin.users.manage seul suffit à s'auto-promouvoir Administrateur ---


def test_user_manager_can_grant_himself_the_administrator_role(env):
    app, client, um = env["app"], env["client"], env["user_manager"]
    _as(app, um)
    before = client.get("/v1/me").json()["privileges"]
    assert before == [Privilege.ADMIN_USERS_MANAGE.value]
    # INVERSÉ par P12.01 (plafond de privilèges) : l'auto-promotion est refusée.
    r = client.patch(f"/v1/users/{um.id}", json={"roleId": env["admin_role_id"]})
    assert r.status_code == 403
    from app.users.models import User

    with env["Session"]() as s:
        fresh = s.get(User, um.id)
        s.expunge(fresh)
    _as(app, fresh)  # utilisateur relu en base après le PATCH
    after = client.get("/v1/me").json()["privileges"]
    assert after == [Privilege.ADMIN_USERS_MANAGE.value]


# --- c01-005 : un lien de partage survit à la perte de droits de son créateur ---


def test_share_link_outlives_creator_rights_on_root_item(env):
    app, client, owner, editor = env["app"], env["client"], env["owner"], env["editor"]
    _as(app, owner)
    item_id = _app_item(client)
    gid = _group_with(client, editor.id)
    body = {"public": False, "groups": [{"groupId": gid, "role": "editor"}]}
    assert client.put(f"/v1/items/{item_id}/sharing", json=body).status_code == 204

    _as(app, editor)
    token = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 30}).json()["token"]

    _as(app, owner)  # le propriétaire retire le partage à l'éditeur
    assert (
        client.put(f"/v1/items/{item_id}/sharing", json={"public": False, "groups": []}).status_code
        == 204
    )
    _as(app, editor)
    assert client.get(f"/v1/items/{item_id}").status_code == 404  # plus aucun droit

    _anonymous(app)
    assert client.get(f"/v1/share-links/{token}").status_code == 200
    r = client.get(f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token})
    assert r.status_code == 200  # la config racine reste servie à l'invité


# --- c01-006 : révocation d'un lien d'un AUTRE item ---


def test_share_access_on_item_a_revokes_link_of_item_b(env):
    app, client, owner, editor = env["app"], env["client"], env["owner"], env["editor"]
    _as(app, owner)
    item_a = _app_item(client, "A")
    item_b = _app_item(client, "B")
    gid = _group_with(client, editor.id)
    body = {"public": False, "groups": [{"groupId": gid, "role": "editor"}]}
    assert client.put(f"/v1/items/{item_a}/sharing", json=body).status_code == 204
    token_b = client.post(f"/v1/items/{item_b}/share-links", json={"ttlDays": 7}).json()["token"]
    link_b = client.get(f"/v1/items/{item_b}/share-links").json()[0]["id"]

    _as(app, editor)
    assert client.get(f"/v1/items/{item_b}").status_code == 404  # B invisible pour lui
    r = client.delete(f"/v1/items/{item_a}/share-links/{link_b}")
    assert r.status_code == 204

    _anonymous(app)
    assert client.get(f"/v1/share-links/{token_b}").status_code == 401  # lien de B révoqué


# --- c01-013 : la liste des partages groupe est servie à tout lecteur ---


def test_any_reader_of_published_item_reads_its_group_sharing(env):
    app, client, owner, editor, viewer = (
        env["app"],
        env["client"],
        env["owner"],
        env["editor"],
        env["viewer"],
    )
    _as(app, owner)
    item_id = _app_item(client)
    gid = _group_with(client, editor.id)
    body = {"public": False, "groups": [{"groupId": gid, "role": "editor"}]}
    assert client.put(f"/v1/items/{item_id}/sharing", json=body).status_code == 204
    assert client.patch(f"/v1/items/{item_id}", json={"isPublished": True}).status_code == 200

    _as(app, viewer)
    r = client.get(f"/v1/items/{item_id}/sharing")
    assert r.status_code == 200
    assert r.json()["groups"] == [{"groupId": gid, "role": "editor"}]
    # alors que le partage lui-même lui est refusé
    assert client.get(f"/v1/items/{item_id}/share-links").status_code == 403
