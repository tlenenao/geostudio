# SPDX-License-Identifier: Apache-2.0
"""Revue finale vague 1 ARC : journal d'entité exact sous limite géographique et masquage,
restauration robuste, fail-closed des routes de modération/qualité/restauration."""

import uuid

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, shape
from shapely.wkt import loads as wkt_loads
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

BASE = "/v1/collections/arc1_fix"
FULL = box(5, 5, 15, 15)  # à cheval sur la limite (0,0)-(10,10)
SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}


class _S3:
    def delete_object(self, *, Bucket, Key):
        pass


def _poly(g):
    return {"type": "Polygon", "coordinates": [[list(c) for c in g.exterior.coords]]}


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS arc1_fix"))
        conn.execute(
            text(
                "CREATE TABLE arc1_fix (id serial PRIMARY KEY, nom text NOT NULL, "
                "salary integer, addr inet, geom geometry(Polygon, 4326))"
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
        role = create_role(
            s, tenant_id=tenant.id, name="editeur", privileges=[Privilege.DATA_VIEW.value]
        )
        editor = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="e",
            username="editor",
            email=None,
            first_name="",
            last_name="",
        )
        editor.role_id = role.id
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="eq", created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=editor.id, tenant_id=tenant.id))
        gid = group.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    client = TestClient(app)

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_optional] = lambda: user

    as_user(admin)
    assert client.post("/v1/collections", json={"tableName": "arc1_fix"}).status_code == 201
    r = client.put(
        f"{BASE}/sharing", json={"public": False, "groups": [{"groupId": gid, "role": "editor"}]}
    )
    assert r.status_code == 200, r.text
    assert client.patch(BASE, json={"sensitiveFields": ["salary"]}).status_code == 200
    created = client.post(
        f"{BASE}/items",
        json={
            "type": "Feature",
            "properties": {"nom": "A", "salary": 100},
            "geometry": _poly(FULL),
        },
    )
    assert created.status_code == 201, created.text
    fid = str(created.json()["id"])

    def limit_editor():
        assert (
            client.put(f"{BASE}/geo-limits/group/{gid}", json={"geometry": SQUARE}).status_code
            == 200
        )

    yield client, as_user, admin, editor, fid, limit_editor, Session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS arc1_fix"))
        conn.execute(
            text(
                "TRUNCATE entity_history, roles, collection_shares, collections, audit_log, "
                "users, tenants CASCADE"
            )
        )


def _versions(client, fid):
    r = client.get(f"{BASE}/items/{fid}/history")
    assert r.status_code == 200, r.text
    return r.json()["versions"]


def test_i2_derived_rule_on_sensitive_field_does_not_break_masked_put(env):
    client, as_user, admin, editor, fid, _limit, Session = env
    rule = {
        "id": "s",
        "kind": "calculation",
        "field": "salary",
        "mode": "derived",
        "expression": "999",
    }
    assert client.patch(BASE, json={"attributeRules": [rule]}).status_code == 200
    as_user(editor)  # masqué (pas data.view_sensitive)
    r = client.put(
        f"{BASE}/items/{fid}",
        json={"type": "Feature", "properties": {"nom": "B"}, "geometry": _poly(FULL)},
    )
    assert r.status_code == 204, r.text
    assert "salary" not in r.text
    with Session() as s:
        row = s.execute(
            text("SELECT nom, salary FROM arc1_fix WHERE id = :i"), {"i": int(fid)}
        ).one()
    assert row == ("B", 100)  # valeur sensible inchangée


def test_i3_restore_on_a_collection_with_an_unsupported_column(env):
    client, _as, admin, _e, fid, _limit, Session = env
    assert (
        client.put(
            f"{BASE}/items/{fid}",
            json={
                "type": "Feature",
                "properties": {"nom": "B", "salary": 1},
                "geometry": _poly(FULL),
            },
        ).status_code
        == 204
    )
    create_id = _versions(client, fid)[-1]["id"]
    assert "addr" in _versions(client, fid)[-1]["after"]["properties"]
    r = client.post(f"{BASE}/items/{fid}/history/{create_id}/restore")
    assert r.status_code == 204, r.text
    with Session() as s:
        row = s.execute(
            text("SELECT nom, salary FROM arc1_fix WHERE id = :i"), {"i": int(fid)}
        ).one()
    assert row == ("A", 100)


def test_i4_journal_keeps_full_geometry_for_a_geo_limited_editor(env):
    client, as_user, admin, editor, fid, limit_editor, Session = env
    limit_editor()
    as_user(editor)
    clipped = client.get(f"{BASE}/items/{fid}").json()["geometry"]
    assert shape(clipped).equals(box(5, 5, 10, 10))
    r = client.put(
        f"{BASE}/items/{fid}",
        json={"type": "Feature", "properties": {"nom": "B"}, "geometry": clipped},
    )
    assert r.status_code == 204, r.text
    as_user(admin)
    latest = _versions(client, fid)[0]
    assert latest["op"] == "update"
    assert shape(latest["before"]["geometry"]).equals(FULL)
    assert shape(latest["after"]["geometry"]).equals(FULL)
    # Restauration (par un non-limité) de cette version : la géométrie n'est pas tronquée.
    assert client.post(f"{BASE}/items/{fid}/history/{latest['id']}/restore").status_code == 204
    with Session() as s:
        wkt = s.execute(
            text("SELECT ST_AsText(geom) FROM arc1_fix WHERE id = :i"), {"i": int(fid)}
        ).scalar()
    assert wkt_loads(wkt).equals(FULL)


def test_i5_moderation_routes_refuse_a_geo_limited_editor(env):
    client, as_user, _a, editor, _fid, limit_editor, _S = env
    limit_editor()
    as_user(editor)
    sid = uuid.uuid4().hex
    assert client.get(f"{BASE}/submissions").status_code == 403
    assert client.get(f"{BASE}/submissions/{sid}/attachment").status_code == 403
    assert client.post(f"{BASE}/submissions/{sid}/approve").status_code == 403
    assert client.post(f"{BASE}/submissions/{sid}/reject", json={}).status_code == 403


def test_m1_quality_reports_refuse_a_geo_limited_reader(env):
    client, as_user, _a, editor, _fid, limit_editor, _S = env
    limit_editor()
    as_user(editor)
    assert client.get(f"{BASE}/quality-checks").status_code == 403
    assert client.get(f"{BASE}/quality-checks/{uuid.uuid4().hex}").status_code == 403


def test_m2_restore_refuses_a_geo_limited_editor(env):
    client, as_user, _a, editor, fid, limit_editor, _S = env
    version_id = _versions(client, fid)[0]["id"]
    limit_editor()
    as_user(editor)
    assert client.post(f"{BASE}/items/{fid}/history/{version_id}/restore").status_code == 403
