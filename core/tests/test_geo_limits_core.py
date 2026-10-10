# SPDX-License-Identifier: Apache-2.0
"""Noyau des limites géographiques (REV-121) : validation de géométrie et
résolution par utilisateur (SQLite, sans RLS — la policy est testée sur PostGIS
dans test_geo_limits_postgis.py)."""

import uuid

import pytest

from app.collections.repository import create_collection
from app.db import init_db, make_engine, make_session_factory
from app.sharing import geo_limits as gl
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
OTHER = {"type": "Polygon", "coordinates": [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]}


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]]},  # nœud
        {"type": "Polygon", "coordinates": [[[0, 0], [500, 0], [500, 10], [0, 0]]]},  # hors WGS84
        {"type": "Polygon", "coordinates": "x"},
    ],
)
def test_validate_rejects(bad):
    with pytest.raises(gl.InvalidGeoLimit):
        gl.validate_limit_geometry(bad)


def test_validate_accepts_and_normalizes():
    out = gl.validate_limit_geometry({**SQUARE, "crs": "ignored"})
    assert out == SQUARE


def test_validate_rejects_too_many_vertices(monkeypatch):
    monkeypatch.setattr(gl, "MAX_VERTICES", 4)
    with pytest.raises(gl.InvalidGeoLimit, match="vertices"):
        gl.validate_limit_geometry(SQUARE)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)

        def user(sub):
            return get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub=sub,
                username=sub,
                email=None,
                first_name="",
                last_name="",
            )

        admin = user("admin")
        alice, bob = user("alice"), user("bob")
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="g", created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=alice.id, tenant_id=tenant.id))
        for name in ("parcelles", "routes"):
            create_collection(
                s,
                tenant_id=tenant.id,
                owner_id=admin.id,
                table_name=name,
                title=name,
                description="",
                is_public=True,
                pk_column="id",
                geometry_column="geom",
                geometry_type="Polygon",
                srid=4326,
            )
        s.commit()
        yield s, tenant, admin, alice, bob, group


def _put(s, tenant, admin, collection, ttype, tid, geom):
    gl.upsert_limit(
        s,
        tenant_id=tenant.id,
        collection_id=collection,
        target_type=ttype,
        target_id=tid,
        geometry=geom,
        actor_id=admin.id,
    )


def test_resolve_by_group_and_role_union(env):
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    _put(s, tenant, admin, "parcelles", "role", alice.role_id, OTHER)
    got = gl.resolve_geo_limits(s, tenant_id=tenant.id, user_id=alice.id)
    assert got == {"parcelles": [SQUARE, OTHER]} or got == {"parcelles": [OTHER, SQUARE]}
    # bob partage le rôle d'alice (même rôle intégré), pas le groupe
    assert alice.role_id == bob.role_id
    assert gl.resolve_geo_limits(s, tenant_id=tenant.id, user_id=bob.id) == {"parcelles": [OTHER]}


def test_resolve_unlimited_without_matching_entry(env):
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    assert gl.resolve_geo_limits(s, tenant_id=tenant.id, user_id=bob.id) == {}


def test_anonymous_sees_nothing_on_any_limited_collection(env):
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    assert gl.resolve_geo_limits(s, tenant_id=None, user_id=None) == {"parcelles": []}


def test_refuse_if_geo_limited():
    gl.refuse_if_geo_limited({}, "t")
    gl.refuse_if_geo_limited(None, "t")
    gl.refuse_if_geo_limited({"other": []}, "t")
    with pytest.raises(gl.GeoLimitRefused) as exc:
        gl.refuse_if_geo_limited({"t": [SQUARE]}, "t", path="aggregates")
    assert exc.value.status_code == 403
    assert "geo_limit_unsupported" in exc.value.detail


def test_upsert_replaces_and_delete(env):
    s, tenant, admin, alice, bob, group = env
    _put(s, tenant, admin, "parcelles", "group", group.id, SQUARE)
    _put(s, tenant, admin, "parcelles", "group", group.id, OTHER)
    rows = gl.list_limits(s, tenant_id=tenant.id, collection_id="parcelles")
    assert len(rows) == 1 and rows[0].geometry == OTHER
    assert gl.delete_limit(
        s, tenant_id=tenant.id, collection_id="parcelles", target_type="group", target_id=group.id
    )
    assert not gl.delete_limit(
        s, tenant_id=tenant.id, collection_id="parcelles", target_type="group", target_id=group.id
    )
