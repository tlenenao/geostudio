# SPDX-License-Identifier: Apache-2.0
"""`ItemRead.permissions` : le cœur calcule, le shell lit.

Objectif produit (spec §6.3) : l'interface ne doit plus proposer une action
que l'API refusera. Ces tests fixent le contrat que `shell/src/auth/Gate.tsx`
consommera.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.main import create_app
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-owner",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        viewer = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-viewer",
            username="viewer",
            email=None,
            first_name="",
            last_name="",
        )
        editor = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-editor",
            username="editor",
            email=None,
            first_name="",
            last_name="",
        )
        stranger = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-stranger",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        gv = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        ge = Group(id="ge", tenant_id=tenant.id, name="E", created_by=owner.id)
        s.add_all([gv, ge])
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=viewer.id, tenant_id=tenant.id))
        s.add(GroupMember(group_id="ge", user_id=editor.id, tenant_id=tenant.id))
        s.add(
            Item(
                id="shared",
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_type="map",
                title="Réseau d'eau potable",
            )
        )
        s.add(
            Item(
                id="pub",
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_type="site",
                title="Portail eau",
                is_published=True,
                slug="portail-eau",
            )
        )
        s.flush()
        s.add(ItemShare(item_id="shared", group_id="gv", tenant_id=tenant.id, role="viewer"))
        s.add(ItemShare(item_id="shared", group_id="ge", tenant_id=tenant.id, role="editor"))
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield {
        "as_user": as_user,
        "owner": owner,
        "viewer": viewer,
        "editor": editor,
        "stranger": stranger,
    }
    engine.dispose()


def _perms(client, item_id: str) -> dict:
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200, response.text
    return response.json()["permissions"]


def test_owner_gets_every_permission(env):
    client = env["as_user"](env["owner"])
    assert _perms(client, "shared") == {"read": True, "write": True, "delete": True, "share": True}


def test_viewer_reads_only(env):
    client = env["as_user"](env["viewer"])
    assert _perms(client, "shared") == {
        "read": True,
        "write": False,
        "delete": False,
        "share": False,
    }


def test_editor_writes_deletes_shares_but_is_not_owner(env):
    client = env["as_user"](env["editor"])
    assert _perms(client, "shared") == {"read": True, "write": True, "delete": True, "share": True}


def test_published_item_is_readable_by_a_stranger_but_not_writable(env):
    client = env["as_user"](env["stranger"])
    assert _perms(client, "pub") == {"read": True, "write": False, "delete": False, "share": False}


def test_listing_carries_the_same_permissions_as_the_detail(env):
    """Le catalogue et la fiche doivent s'accorder : c'est la colonne
    « Votre accès » de la maquette qui en dépend."""
    client = env["as_user"](env["viewer"])
    listing = client.get("/items?scope=all&pageSize=50")
    assert listing.status_code == 200, listing.text
    by_pk = {item["pk"]: item for item in listing.json()["items"]}
    assert by_pk["shared"]["permissions"] == _perms(client, "shared")
    assert by_pk["shared"]["permissions"]["write"] is False


def test_patch_response_reflects_the_write_that_just_succeeded(env):
    """La réponse d'un PATCH réussi doit refléter le verdict réel, pas le
    repli conservateur : la requête qui vient de réussir prouve déjà
    `write: true` (Finding I1, Problème A)."""
    client = env["as_user"](env["owner"])
    response = client.patch("/items/shared", json={"title": "Réseau d'eau potable (v2)"})
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == {
        "read": True,
        "write": True,
        "delete": True,
        "share": True,
    }


def test_public_route_serves_the_conservative_default(env):
    """`GET /public/items` est anonyme : personne n'a de droit d'écriture,
    et le champ doit quand même être présent — le shell le lit sans savoir
    par quelle route l'item est arrivé."""
    client = env["as_user"](env["stranger"])
    response = client.get("/public/items")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "au moins l'item publié doit ressortir"
    for item in items:
        assert item["permissions"] == {
            "read": True,
            "write": False,
            "delete": False,
            "share": False,
        }
