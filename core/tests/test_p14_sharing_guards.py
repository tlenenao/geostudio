# SPDX-License-Identifier: Apache-2.0
"""P14 (RC-7, partage/groupes/liens) : gardes de privilège de kind sur la
publication/le partage/les liens, IDOR de révocation, liens qui meurent avec
les droits de leur créateur, CRUD de groupes. SQLite en mémoire."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.service import get_sharing_service, set_sharing_service
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.sharing.schemas import Sharing
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "p14-share-link-secret-padding-000000")


def _user(s, tenant_id, sub, role=None, **kw):
    u = get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=sub,
        username=sub,
        email=f"{sub}@x.test",
        first_name="",
        last_name="",
        **kw,
    )
    if role:
        u.role_id = ensure_built_in_roles(s, tenant_id=tenant_id)[role].id
        u.is_admin = role == "admin"
    return u


def _no_privilege_user(env):
    from app.roles.repository import create_role

    with env["Session"]() as s:
        t = get_or_create_default_tenant(s)
        u = _user(s, t.id, "nobody", None)
        u.role_id = create_role(s, tenant_id=t.id, name="Aucun", privileges=[]).id
        s.commit()
        s.refresh(u)
        s.expunge(u)
        return u


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        owner = _user(s, t.id, "owner", "creator")
        admin = _user(s, t.id, "admin", "admin")
        reader = _user(s, t.id, "reader", "reader")
        other = _user(s, t.id, "other", "creator")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    yield {
        "app": app,
        "client": TestClient(app),
        "Session": Session,
        "owner": owner,
        "admin": admin,
        "reader": reader,
        "other": other,
    }
    engine.dispose()


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _anon(app):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


def _app_item(client, title="App") -> str:
    body = {"kind": "app", "dataSources": [], "layout": {"type": "grid", "items": []}}
    r = client.post("/v1/configs", json={"title": title, "config": body})
    assert r.status_code == 201, r.text
    return r.json()["itemId"]


def _group(client, *members) -> str:
    gid = client.post("/v1/groups", json={"name": "equipe"}).json()["id"]
    for m in members:
        assert client.post(f"/v1/groups/{gid}/members", json={"userId": m.id}).status_code == 204
    return gid


def _share(client, item_id, gid, role="manager"):
    body = {"public": False, "groups": [{"groupId": gid, "role": role}]}
    assert client.put(f"/v1/items/{item_id}/sharing", json=body).status_code == 204


# --- P14.01 (j13-002) : le rôle de partage ne suffit pas, le privilège du kind aussi ---


def test_reader_with_editor_share_cannot_publish_reshare_or_link(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    gid = _group(c, env["reader"])
    _share(c, item, gid)

    _as(app, env["reader"])
    assert c.get(f"/v1/items/{item}").status_code == 200  # lecture : oui
    assert c.patch(f"/v1/items/{item}", json={"isPublished": True}).status_code == 403
    assert c.patch(f"/v1/items/{item}", json={"title": "pwn"}).status_code == 403
    assert c.get(f"/v1/items/{item}/sharing").status_code == 403
    r = c.put(f"/v1/items/{item}/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403
    assert c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 1}).status_code == 403
    assert c.get(f"/v1/items/{item}/share-links").status_code == 403


def test_sharing_service_twin_of_mcp_set_sharing_has_the_same_guard(env):
    # app.mcp.tools.sharing.set_sharing/get_sharing appellent ces deux fonctions.
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    _share(c, item, _group(c, env["reader"]))
    with env["Session"]() as s:
        from app.users.models import User

        reader = s.get(User, env["reader"].id)
        for call in (
            lambda: set_sharing_service(
                s,
                item_id=item,
                user=reader,
                sharing=Sharing(public=True, groups=[]),
                actor_kind="agent",
            ),
            lambda: get_sharing_service(s, item_id=item, user=reader),
        ):
            with pytest.raises(HTTPException) as exc:
                call()
            assert exc.value.status_code == 403


def test_creator_still_publishes_and_shares(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    assert c.patch(f"/v1/items/{item}", json={"isPublished": True}).status_code == 200
    assert c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 1}).status_code == 201


# --- P14.06 (c01-006, c08-001) : révocation limitée à l'item vérifié ---


def test_revoke_refuses_a_link_of_another_item(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    a, b = _app_item(c, "A"), _app_item(c, "B")
    _share(c, a, _group(c, env["other"]))
    token_b = c.post(f"/v1/items/{b}/share-links", json={"ttlDays": 7}).json()["token"]
    link_b = c.get(f"/v1/items/{b}/share-links").json()[0]["id"]

    _as(app, env["other"])
    assert c.delete(f"/v1/items/{a}/share-links/{link_b}").status_code == 404
    _anon(app)
    assert c.get(f"/v1/share-links/{token_b}").status_code == 200  # toujours actif


# --- REV-270 / P14.12 : « peut modifier » (editor) ≠ « peut gérer le partage » (manager) ---


def test_editor_modifies_but_cannot_manage_sharing_manager_can(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    gid = _group(c, env["other"])
    _share(c, item, gid, "editor")

    _as(app, env["other"])
    perms = c.get(f"/v1/items/{item}").json()["permissions"]
    assert perms == {"read": True, "write": True, "delete": True, "share": False}
    assert c.get(f"/v1/items/{item}/sharing").status_code == 403
    r = c.put(f"/v1/items/{item}/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403
    assert c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 1}).status_code == 403

    _as(app, env["owner"])
    _share(c, item, gid, "manager")
    _as(app, env["other"])
    assert c.get(f"/v1/items/{item}").json()["permissions"]["share"] is True
    assert c.get(f"/v1/items/{item}/sharing").status_code == 200
    assert c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 1}).status_code == 201


# --- P14.13 (c01-005) : le lien meurt avec les droits de son créateur ---


def test_share_link_stops_when_creator_loses_rights_on_root_item(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    _share(c, item, _group(c, env["other"]))
    _as(app, env["other"])
    token = c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 30}).json()["token"]
    _anon(app)
    assert c.get(f"/v1/share-links/{token}").status_code == 200

    _as(app, env["owner"])
    assert (
        c.put(f"/v1/items/{item}/sharing", json={"public": False, "groups": []}).status_code == 204
    )
    _anon(app)
    assert c.get(f"/v1/share-links/{token}").status_code == 401
    r = c.get(f"/v1/configs/by-item/{item}", headers={"X-Share-Link-Token": token})
    assert r.status_code in (401, 403, 404)


# --- P14.02 (j13-004) + P14.08 (j13-006) : CRUD de groupes ---


def test_group_creator_lists_removes_renames_and_deletes(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    gid = _group(c, env["other"])
    _share(c, item, gid, "viewer")
    g = c.get("/v1/groups").json()[0]
    assert g["canManage"] is True and g["createdBy"] == env["owner"].id

    members = c.get(f"/v1/groups/{gid}/members").json()
    assert [m["userId"] for m in members] == [env["other"].id]
    assert c.patch(f"/v1/groups/{gid}", json={"name": "renomme"}).json()["name"] == "renomme"

    _as(app, env["other"])
    assert c.get(f"/v1/items/{item}").status_code == 200
    _as(app, env["owner"])
    assert c.delete(f"/v1/groups/{gid}/members/{env['other'].id}").status_code == 204
    assert c.delete(f"/v1/groups/{gid}/members/{env['other'].id}").status_code == 404
    _as(app, env["other"])
    assert c.get(f"/v1/items/{item}").status_code == 404  # retrait = accès coupé

    _as(app, env["owner"])
    assert c.delete(f"/v1/groups/{gid}").status_code == 204
    assert c.get("/v1/groups").json() == []
    assert c.get(f"/v1/items/{item}/sharing").json()["groups"] == []  # partages purgés


def test_group_management_is_for_creator_or_user_admin_only(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    gid = _group(c, env["reader"])
    _as(app, env["other"])  # Créateur d'un autre groupe : pas celui-ci
    assert c.get("/v1/groups").json()[0]["canManage"] is False
    assert c.get(f"/v1/groups/{gid}/members").status_code == 404
    assert c.patch(f"/v1/groups/{gid}", json={"name": "x"}).status_code == 404
    assert c.delete(f"/v1/groups/{gid}").status_code == 404
    _as(app, env["admin"])
    assert len(c.get(f"/v1/groups/{gid}/members").json()) == 1
    assert c.patch(f"/v1/groups/{gid}", json={"name": "ok"}).status_code == 200
    assert c.delete(f"/v1/groups/{gid}").status_code == 204


# --- P14.07 (j13-005) : annuaire restreint ---


def test_directory_search_is_for_catalog_managers_and_exposes_no_role(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    r = c.get("/v1/users/directory", params={"q": "OTH"})
    assert r.status_code == 200
    assert r.json() == [{"id": env["other"].id, "username": "other", "email": "other@x.test"}]
    assert c.get("/v1/users/directory", params={"q": "%%"}).json() == []  # littéral
    assert c.get("/v1/users/directory", params={"q": "o"}).status_code == 422
    # Un rôle sur mesure sans aucun privilège (le Lecteur porte analytics.view
    # depuis REV-270/P12.10, donc peut partager ses bookmarks) reste refusé.
    _as(app, _no_privilege_user(env))
    assert c.get("/v1/users/directory", params={"q": "oth"}).status_code == 403


def test_analyst_who_can_share_a_bookmark_can_list_groups_and_search_directory(env):
    # Revue finale : GET /groups exigeait catalog.manage alors que le partage
    # d'un item exige le privilège de son kind (bookmark = analytics.view,
    # Analyste sans catalog.manage) -> ShareForm (qui exige les groupes
    # chargés) restait en échec pour qui a pourtant le droit de partager.
    with env["Session"]() as s:
        t = get_or_create_default_tenant(s)
        analyst = _user(s, t.id, "analyst1", "analyst")
        s.commit()
    app, c = env["app"], env["client"]
    _as(app, analyst)
    assert c.get("/v1/groups").status_code == 200
    assert c.get("/v1/users/directory", params={"q": "oth"}).status_code == 200
    # Le Lecteur (analytics.view, REV-270/P12.10) partage ses bookmarks : OK.
    _as(app, env["reader"])
    assert c.get("/v1/groups").status_code == 200
    _as(app, _no_privilege_user(env))
    assert c.get("/v1/groups").status_code == 403


# --- P14.10/P14.11 (j13-011/012) : lien vers une page du shell, liste lisible ---


def test_share_link_url_targets_the_shell_embed_page_and_list_names_creator(env, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://gis.example.test/")
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    created = c.post(f"/v1/items/{item}/share-links", json={"ttlDays": 2}).json()
    assert created["url"] == f"https://gis.example.test/embed/{created['token']}"
    row = c.get(f"/v1/items/{item}/share-links").json()[0]
    assert row["createdBy"] == "owner" and row["createdAt"]


# --- P14.05 (j13-010) : permissions = rôle de partage ET privilège de kind ---


def test_item_permissions_combine_share_role_and_kind_privilege(env):
    app, c = env["app"], env["client"]
    _as(app, env["owner"])
    item = _app_item(c)
    _share(c, item, _group(c, env["reader"], env["other"]))
    all_true = {"read": True, "write": True, "delete": True, "share": True}
    assert c.get(f"/v1/items/{item}").json()["permissions"] == all_true
    _as(app, env["other"])  # Créateur : privilège de kind + rôle editor
    assert c.get(f"/v1/items/{item}").json()["permissions"] == all_true
    _as(app, env["reader"])  # rôle editor mais 0 privilège
    assert c.get(f"/v1/items/{item}").json()["permissions"] == {
        "read": True,
        "write": False,
        "delete": False,
        "share": False,
    }
