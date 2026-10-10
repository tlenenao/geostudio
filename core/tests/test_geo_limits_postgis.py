# SPDX-License-Identifier: Apache-2.0
"""Policy RLS restrictive `geo_limit` sur PostGIS réel (REV-121, spec §2.2/§6)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.collections.ddl import apply_collection_ddl, sync_masked_role_grants
from app.collections.introspection_pg import introspect_table
from app.features import repository as repo
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
OTHER = {"type": "Polygon", "coordinates": [[[40, 40], [60, 40], [60, 60], [40, 60], [40, 40]]]}
INSIDE = {"type": "Point", "coordinates": [5, 5]}
OUTSIDE = {"type": "Point", "coordinates": [50, 50]}


@pytest.fixture()
def pts(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_pts, gl_merc"))
        conn.execute(
            text(
                "CREATE TABLE gl_pts (id serial PRIMARY KEY, name text, geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO gl_pts (name, geom) VALUES "
                "('in', ST_SetSRID(ST_MakePoint(5, 5), 4326)), "
                "('out', ST_SetSRID(ST_MakePoint(50, 50), 4326)), "
                "('nogeom', NULL), "
                "('edge', ST_SetSRID(ST_MakePoint(10, 10), 4326))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE gl_merc (id serial PRIMARY KEY, name text, "
                "geom geometry(Point, 3857))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO gl_merc (name, geom) VALUES "
                "('in', ST_Transform(ST_SetSRID(ST_MakePoint(5, 5), 4326), 3857)), "
                "('out', ST_Transform(ST_SetSRID(ST_MakePoint(50, 50), 4326), 3857))"
            )
        )
    with pg_session_factory() as session:
        apply_collection_ddl(session, "gl_pts", tenant_id="default")
        apply_collection_ddl(session, "gl_merc", tenant_id="default")
        session.commit()
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_pts, gl_merc"))


def _names(session, table="gl_pts", **scope):
    with rls_scope(session, "default", **scope):
        return sorted(session.execute(text(f"SELECT name FROM {table}")).scalars())


def test_unrestricted_sees_everything(pts, pg_session_factory):
    with pg_session_factory() as s:
        assert _names(s) == ["edge", "in", "nogeom", "out"]
        assert _names(s, geo_limits={}) == ["edge", "in", "nogeom", "out"]
        # une limite sur une AUTRE table ne s'applique pas à celle-ci
        assert _names(s, geo_limits={"autre": [SQUARE]}) == ["edge", "in", "nogeom", "out"]


def test_limited_sees_only_contained_geometries(pts, pg_session_factory):
    with pg_session_factory() as s:
        # contenu strict, bord inclus ; géométrie NULL invisible (fail-closed)
        assert _names(s, geo_limits={"gl_pts": [SQUARE]}) == ["edge", "in"]
        # union de plusieurs géométries
        assert _names(s, geo_limits={"gl_pts": [SQUARE, OTHER]}) == ["edge", "in", "out"]
        # liste vide (anonyme) : rien
        assert _names(s, geo_limits={"gl_pts": []}) == []


def test_masked_role_is_limited_too(pts, pg_session_factory):
    with pg_session_factory() as s:
        sync_masked_role_grants(s, "gl_pts", [])
        assert _names(s, masked=True, geo_limits={"gl_pts": [SQUARE]}) == ["edge", "in"]


def test_other_srid_is_reprojected(pts, pg_session_factory):
    with pg_session_factory() as s:
        assert _names(s, "gl_merc", geo_limits={"gl_merc": [SQUARE]}) == ["in"]


def test_scope_resets_limits_between_scopes(pts, pg_session_factory):
    with pg_session_factory() as s:
        assert _names(s, geo_limits={"gl_pts": []}) == []
        assert _names(s) == ["edge", "in", "nogeom", "out"]  # pas de valeur périmée


def test_repository_reads_respect_limit(pts, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_pts")
        with rls_scope(s, "default", geo_limits={"gl_pts": [SQUARE]}):
            page = repo.select_features(s, info, limit=10, offset=0, count_mode="exact")
            assert sorted(f["properties"]["name"] for f in page.features) == ["edge", "in"]
            assert page.number_matched == 2
            out_fid = s.execute(text("SELECT id FROM gl_pts WHERE name = 'out'")).scalar()
            assert repo.get_feature(s, info, fid=str(out_fid)) is None
            # bbox qui couvre l'extérieur : ne le révèle pas
            page = repo.select_features(
                s, info, limit=10, offset=0, bbox=(40, 40, 60, 60), count_mode="exact"
            )
            assert page.features == [] and page.number_matched == 0


def test_write_outside_limit_is_refused(pts, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_pts")
        limits = {"gl_pts": [SQUARE]}
        with rls_scope(s, "default", geo_limits=limits):
            assert repo.insert_feature(s, info, properties={"name": "new"}, geometry=INSIDE)
        with pytest.raises(DBAPIError) as exc:
            with rls_scope(s, "default", geo_limits=limits):
                repo.insert_feature(s, info, properties={"name": "bad"}, geometry=OUTSIDE)
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()
        with pytest.raises(DBAPIError) as exc:  # géométrie NULL aussi refusée
            with rls_scope(s, "default", geo_limits=limits):
                repo.insert_feature(s, info, properties={"name": "nog"}, geometry=None)
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()
        # déplacer une entité visible hors limite : refusé
        fid = s.execute(text("SELECT id FROM gl_pts WHERE name = 'in'")).scalar()
        with pytest.raises(DBAPIError) as exc:
            with rls_scope(s, "default", geo_limits=limits):
                repo.replace_feature(
                    s, info, fid=str(fid), properties={"name": "in"}, geometry=OUTSIDE
                )
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()


def test_hidden_entities_cannot_be_updated_or_deleted(pts, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_pts")
        out = str(s.execute(text("SELECT id FROM gl_pts WHERE name = 'out'")).scalar())
        with rls_scope(s, "default", geo_limits={"gl_pts": [SQUARE]}):
            assert (
                repo.replace_feature(s, info, fid=out, properties={"name": "x"}, geometry=INSIDE)
                is False
            )
            assert repo.delete_feature(s, info, fid=out) is False
            assert repo.delete_all_features(s, info) == 2  # seulement edge + in
        s.rollback()
        assert _names(s) == ["edge", "in", "nogeom", "out"]


def test_policy_is_idempotent_and_installed_by_apply_ddl(pts, pg_session_factory):
    from app.collections.ddl import ensure_geo_limit_policy

    with pg_session_factory() as s:
        assert ensure_geo_limit_policy(s, "gl_pts") is True
        assert ensure_geo_limit_policy(s, "gl_pts") is True
        n = s.execute(
            text(
                "SELECT count(*) FROM pg_policies "
                "WHERE tablename='gl_pts' AND policyname LIKE 'geo_limit_%'"
            )
        ).scalar()
        assert n == 4  # select/insert/update/delete ; la policy unique de la v1 a disparu
        assert _names(s, geo_limits={"gl_pts": [SQUARE]}) == ["edge", "in"]


def test_table_without_geometry_gets_no_policy(pg_engine, pg_session_factory):
    from app.collections.ddl import ensure_geo_limit_policy

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_flat"))
        conn.execute(text("CREATE TABLE gl_flat (id serial PRIMARY KEY, v text)"))
    try:
        with pg_session_factory() as s:
            assert ensure_geo_limit_policy(s, "gl_flat") is False
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS gl_flat"))
