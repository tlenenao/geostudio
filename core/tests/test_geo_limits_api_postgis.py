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


def test_removing_the_limit_restores_full_access(env):
    client, _, as_user, admin, regular, gid = env
    assert _limit(client, gid).status_code == 200
    assert client.delete(f"{BASE}/geo-limits/group/{gid}").status_code == 204
    as_user(regular)
    assert _titles(client.get(f"{BASE}/items")) == ["in", "out"]
