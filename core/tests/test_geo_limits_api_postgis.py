# SPDX-License-Identifier: Apache-2.0
"""Limites géographiques de bout en bout (REV-121) : routes d'administration puis
lecture/écriture par un utilisateur limité sur PostGIS réel (RLS, pas de filtre
applicatif). Chaque chemin de lecture que la limite ne sait pas couvrir doit
refuser (403 geo_limit_unsupported), jamais fuiter."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

BASE = "/v1/collections/gl_api"
SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
SELF_INTERSECTING = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]],
}


def _feature(titre, lon, lat):
    return {
        "type": "Feature",
        "properties": {"titre": titre},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_api"))
        conn.execute(
            text(
                "CREATE TABLE gl_api (id serial PRIMARY KEY, titre text, "
                "geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
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
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="eq", created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=regular.id, tenant_id=tenant.id))
        group_id = group.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_optional] = lambda: user

    as_user(admin)
    assert (
        client.post("/v1/collections", json={"tableName": "gl_api", "isPublic": True}).status_code
        == 201
    )
    r = client.put(
        f"{BASE}/sharing",
        json={"public": True, "groups": [{"groupId": group_id, "role": "editor"}]},
    )
    assert r.status_code == 200, r.text
    assert client.post(f"{BASE}/items", json=_feature("in", 5, 5)).status_code == 201
    assert client.post(f"{BASE}/items", json=_feature("out", 50, 50)).status_code == 201
    yield client, app, as_user, admin, regular, group_id
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_api"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _titles(r):
    assert r.status_code == 200, r.text
    return sorted(f["properties"]["titre"] for f in r.json()["features"])


def _limit(client, group_id, geometry=SQUARE):
    return client.put(f"{BASE}/geo-limits/group/{group_id}", json={"geometry": geometry})


def test_admin_routes_crud_validation_and_audit(env, pg_engine):
    client, _, as_user, admin, regular, gid = env
    assert client.get(f"{BASE}/geo-limits").json() == {"limits": []}
    r = _limit(client, gid)
    assert r.status_code == 200 and r.json()["targetId"] == gid
    assert _limit(client, gid).status_code == 200  # upsert
    assert len(client.get(f"{BASE}/geo-limits").json()["limits"]) == 1
    assert _limit(client, gid, SELF_INTERSECTING).status_code == 422
    assert _limit(client, gid, {"type": "Point", "coordinates": [0, 0]}).status_code == 422
    assert (
        client.put(f"{BASE}/geo-limits/group/inconnu", json={"geometry": SQUARE}).status_code == 404
    )
    assert client.put(f"{BASE}/geo-limits/user/{gid}", json={"geometry": SQUARE}).status_code == 422
    # un non-administrateur de collections n'y touche pas
    as_user(regular)
    assert client.get(f"{BASE}/geo-limits").status_code == 403
    assert _limit(client, gid).status_code == 403
    as_user(admin)
    with pg_engine.begin() as conn:
        actions = set(conn.execute(text("SELECT action FROM audit_log")).scalars())
    assert "geo_limit.set" in actions
    assert client.delete(f"{BASE}/geo-limits/group/{gid}").status_code == 204
    assert client.delete(f"{BASE}/geo-limits/group/{gid}").status_code == 404
    with pg_engine.begin() as conn:
        actions = set(conn.execute(text("SELECT action FROM audit_log")).scalars())
    assert "geo_limit.delete" in actions


def test_limited_member_reads_only_inside(env):
    client, _, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    as_user(regular)
    assert _titles(client.get(f"{BASE}/items")) == ["in"]
    # l'entité hors limite n'existe pas pour lui, même par son id
    as_user(admin)
    out_fid = next(
        f["id"]
        for f in client.get(f"{BASE}/items").json()["features"]
        if f["properties"]["titre"] == "out"
    )
    as_user(regular)
    assert client.get(f"{BASE}/items/{out_fid}").status_code == 404
    # bbox englobant l'extérieur : rien de plus
    assert _titles(client.get(f"{BASE}/items", params={"bbox": "40,40,60,60"})) == []
    # tuile : l'entité hors limite n'y figure pas
    tile = client.get(f"{BASE}/tiles/0/0/0.mvt")
    assert (
        tile.status_code == 200
        and b"in" in tile.content
        and b"out" not in tile.content.replace(b"count", b"")
    )
    # le compteur global ne fuit pas
    assert client.get(BASE).json()["featureCount"] is None
    # l'administrateur (sans limite) voit tout
    as_user(admin)
    assert _titles(client.get(f"{BASE}/items")) == ["in", "out"]
    assert client.get(BASE).json()["featureCount"] == 2


def test_anonymous_sees_nothing_on_a_limited_public_collection(env):
    client, app, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    as_user(None)
    assert _titles(client.get(f"{BASE}/items")) == []


def test_write_outside_limit_is_a_403_and_inside_is_fine(env):
    client, _, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    as_user(regular)
    assert client.post(f"{BASE}/items", json=_feature("new-in", 1, 1)).status_code == 201
    r = client.post(f"{BASE}/items", json=_feature("new-out", 60, 60))
    assert r.status_code == 403 and "outside_geo_limit" in r.text
    in_fid = next(
        f["id"]
        for f in client.get(f"{BASE}/items").json()["features"]
        if f["properties"]["titre"] == "new-in"
    )
    r = client.put(f"{BASE}/items/{in_fid}", json=_feature("moved", 60, 60))
    assert r.status_code == 403 and "outside_geo_limit" in r.text


def test_lake_and_attachment_paths_refuse(env):
    client, _, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    as_user(regular)
    r = client.post(f"{BASE}/aggregate", json={"agg": "count"})
    assert r.status_code == 403 and "geo_limit_unsupported" in r.text
    r = client.get(f"{BASE}/items/1/attachments")
    assert r.status_code == 403 and "geo_limit_unsupported" in r.text
    # sans limite (admin), le refus ne s'applique pas
    as_user(admin)
    assert client.get(f"{BASE}/items/1/attachments").status_code == 200


def test_a_role_holding_admin_collections_manage_cannot_be_limited(env):
    client, _, as_user, admin, regular, gid = env
    r = client.put(f"{BASE}/geo-limits/role/{admin.role_id}", json={"geometry": SQUARE})
    assert r.status_code == 422 and "admin.collections.manage" in r.text
    # un rôle sans ce privilège reste limitable
    assert (
        client.put(
            f"{BASE}/geo-limits/role/{regular.role_id}", json={"geometry": SQUARE}
        ).status_code
        == 200
    )


def test_unique_collision_with_a_hidden_row_is_indistinguishable(env, pg_engine):
    """(4) Un INSERT/UPDATE qui collisionne avec une ligne CACHÉE par la limite répond
    exactement comme une collision avec une ligne visible (même 409, même corps) ; une PK
    choisie par le client n'est de toute façon pas acceptée."""
    client, _, as_user, admin, regular, gid = env
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX gl_api_titre_uq ON gl_api (titre)"))
    assert _limit(client, gid).status_code == 200
    as_user(regular)
    visible = client.post(f"{BASE}/items", json=_feature("in", 1, 1))
    hidden = client.post(f"{BASE}/items", json=_feature("out", 2, 2))
    assert visible.status_code == hidden.status_code == 409
    assert visible.json() == hidden.json()
    # même chose par PUT : renommer une entité visible vers un titre déjà pris (caché / visible)
    as_user(admin)
    ok = client.post(f"{BASE}/items", json=_feature("tmp", 3, 3))
    assert ok.status_code == 201
    as_user(regular)
    to_hidden = client.put(f"{BASE}/items/{ok.json()['id']}", json=_feature("out", 3, 3))
    to_visible = client.put(f"{BASE}/items/{ok.json()['id']}", json=_feature("in", 3, 3))
    assert to_hidden.status_code == to_visible.status_code == 409
    assert to_hidden.json() == to_visible.json()
    # PK client : même réponse que la ligne cible soit visible ou cachée
    as_user(admin)
    fids = {
        f["properties"]["titre"]: f["id"] for f in client.get(f"{BASE}/items").json()["features"]
    }
    as_user(regular)
    pk_visible = client.post(f"{BASE}/items", json={**_feature("n1", 4, 4), "id": fids["in"]})
    pk_hidden = client.post(f"{BASE}/items", json={**_feature("n2", 4, 4), "id": fids["out"]})
    # l'`id` de premier niveau est ignoré : lignes neuves, aucune ligne existante touchée
    assert pk_visible.status_code == pk_hidden.status_code == 201
    assert {pk_visible.json()["id"], pk_hidden.json()["id"]}.isdisjoint(fids.values())
    pk_prop_visible = client.post(
        f"{BASE}/items",
        json={**_feature("n3", 5, 5), "properties": {"titre": "n3", "id": fids["in"]}},
    )
    pk_prop_hidden = client.post(
        f"{BASE}/items",
        json={**_feature("n4", 5, 5), "properties": {"titre": "n4", "id": fids["out"]}},
    )
    assert pk_prop_visible.status_code == pk_prop_hidden.status_code
    assert pk_prop_visible.json() == pk_prop_hidden.json()


@pytest.fixture()
def poly_env(env, pg_engine):
    client, app, as_user, admin, regular, gid = env
    from unittest.mock import MagicMock

    from app.attachments import routes as attachments_routes

    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: MagicMock()
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_apip"))
        conn.execute(
            text(
                "CREATE TABLE gl_apip (id serial PRIMARY KEY, titre text, "
                "geom geometry(Polygon, 4326))"
            )
        )
    assert (
        client.post("/v1/collections", json={"tableName": "gl_apip", "isPublic": True}).status_code
        == 201
    )
    r = client.put(
        "/v1/collections/gl_apip/sharing",
        json={"public": True, "groups": [{"groupId": gid, "role": "editor"}]},
    )
    assert r.status_code == 200, r.text
    ring = [[5, 5], [15, 5], [15, 15], [5, 15], [5, 5]]
    feature = {
        "type": "Feature",
        "properties": {"titre": "straddle"},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    assert client.post("/v1/collections/gl_apip/items", json=feature).status_code == 201
    far = [[40, 40], [50, 40], [50, 50], [40, 50], [40, 40]]
    far_feature = {
        **feature,
        "properties": {"titre": "far"},
        "geometry": {"type": "Polygon", "coordinates": [far]},
    }
    assert client.post("/v1/collections/gl_apip/items", json=far_feature).status_code == 201
    assert (
        client.put(
            f"/v1/collections/gl_apip/geo-limits/group/{gid}", json={"geometry": SQUARE}
        ).status_code
        == 200
    )
    yield client, as_user, admin, regular, pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_apip"))


def _max_xy(geometry) -> float:
    def walk(c):
        return [c] if isinstance(c[0], (int, float)) else [p for x in c for p in walk(x)]

    return max(max(p) for p in walk(geometry["coordinates"]))


def test_clipping_on_every_http_read_path(poly_env):
    client, as_user, admin, regular, _ = poly_env
    P = "/v1/collections/gl_apip"
    as_user(regular)
    items = client.get(f"{P}/items").json()
    assert [f["properties"]["titre"] for f in items["features"]] == ["straddle"]
    feat = items["features"][0]
    assert _max_xy(feat["geometry"]) <= 10  # jamais la géométrie complète (15)
    assert _max_xy(client.get(f"{P}/items/{feat['id']}").json()["geometry"]) <= 10
    # sonder la partie cachée par bbox : rien
    assert client.get(f"{P}/items", params={"bbox": "11,11,14,14"}).json()["features"] == []
    # tuile : 200 et jamais la géométrie hors limite (sondée via le résultat de la route)
    assert client.get(f"{P}/tiles/0/0/0.mvt").status_code == 200
    # emprise de la collection (OGC) et STAC : celles du découpé
    assert client.get(P).json()["extent"]["spatial"]["bbox"] == [[5.0, 5.0, 10.0, 10.0]]
    stac = client.get("/v1/stac/collections/gl_apip").json()
    assert stac["extent"]["spatial"]["bbox"] == [[5.0, 5.0, 10.0, 10.0]]
    s_items = client.get("/v1/stac/collections/gl_apip/items").json()
    assert all(_max_xy(f["geometry"]) <= 10 and max(f["bbox"]) <= 10 for f in s_items["features"])
    search = client.post("/v1/stac/search", json={"collections": ["gl_apip"]}).json()
    assert all(max(f["bbox"]) <= 10 for f in search["features"])
    # le propriétaire non limité (admin) voit la géométrie complète
    as_user(admin)
    full = client.get(f"{P}/items").json()["features"]
    assert max(_max_xy(f["geometry"]) for f in full) == 50


def test_straddling_entity_http_write_rules(poly_env):
    client, as_user, admin, regular, pg_engine = poly_env
    P = "/v1/collections/gl_apip"
    as_user(regular)
    feat = client.get(f"{P}/items").json()["features"][0]
    with pg_engine.connect() as conn:
        before = conn.execute(
            text("SELECT ST_AsText(geom) FROM gl_apip WHERE id = :i"), {"i": feat["id"]}
        ).scalar()
    # attributs seulement, avec la géométrie DÉCOUPÉE renvoyée telle quelle : accepté
    ok = client.put(f"{P}/items/{feat['id']}", json={**feat, "properties": {"titre": "renamed"}})
    assert ok.status_code == 204, ok.text
    with pg_engine.connect() as conn:
        row = conn.execute(
            text("SELECT titre, ST_AsText(geom) FROM gl_apip WHERE id = :i"), {"i": feat["id"]}
        ).one()
    assert row[0] == "renamed" and row[1] == before  # partie cachée intacte
    # géométrie modifiée : refusée (fail-closed)
    moved = {
        **feat,
        "geometry": {"type": "Polygon", "coordinates": [[[6, 6], [9, 6], [9, 9], [6, 9], [6, 6]]]},
    }
    r = client.put(f"{P}/items/{feat['id']}", json=moved)
    assert r.status_code == 403 and "geo_limit_straddling" in r.text
    # suppression : introuvable pour l'utilisateur limité (la partie cachée serait détruite)
    assert client.delete(f"{P}/items/{feat['id']}").status_code == 404
    # création à cheval : refusée
    crossing = {
        **feat,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[8, 8], [12, 8], [12, 12], [8, 12], [8, 8]]],
        },
    }
    crossing.pop("id", None)
    r = client.post(f"{P}/items", json=crossing)
    assert r.status_code == 403 and "outside_geo_limit" in r.text


def test_removing_the_limit_restores_full_access(env):
    client, _, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    assert client.delete(f"{BASE}/geo-limits/group/{gid}").status_code == 204
    as_user(regular)
    assert _titles(client.get(f"{BASE}/items")) == ["in", "out"]
