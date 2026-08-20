# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace

import pytest
from sqlalchemy import text

from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.features.repository import (
    FilterError,
    delete_feature,
    get_feature,
    insert_feature,
    replace_feature,
    select_features,
)
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_incidents(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))
        conn.execute(
            text(
                "CREATE TABLE t_feat (id serial PRIMARY KEY, titre text NOT NULL, "
                "nb integer, tenant_id text NOT NULL DEFAULT 'default', "
                "geom geometry(Point, 4326))"
            )
        )
        conn.execute(text("ALTER TABLE t_feat ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation ON t_feat "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_feat TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_feat_id_seq TO gis_rls"))
        conn.execute(
            text(
                "INSERT INTO t_feat (titre, nb, tenant_id, geom) VALUES "
                "('a', 1, 'default', ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326)), "
                "('b', 2, 'default', ST_SetSRID(ST_MakePoint(2.0, 46.0), 4326)), "
                "('c', 3, 'other',   ST_SetSRID(ST_MakePoint(3.0, 47.0), 4326))"
            )
        )
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))


@pytest.fixture()
def info(pg_incidents, pg_session_factory):
    with pg_session_factory() as session:
        yield introspect_table(session, "t_feat")


@pytest.fixture()
def pg_incidents_l93(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat_l93"))
        conn.execute(
            text(
                "CREATE TABLE t_feat_l93 (id serial PRIMARY KEY, titre text NOT NULL, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 2154))"
            )
        )
        conn.execute(text("ALTER TABLE t_feat_l93 ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation ON t_feat_l93 "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_feat_l93 TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_feat_l93_id_seq TO gis_rls"))
        conn.execute(
            text(
                "INSERT INTO t_feat_l93 (titre, tenant_id, geom) VALUES "
                "('a', 'default', ST_Transform(ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326), 2154)), "
                "('b', 'default', ST_Transform(ST_SetSRID(ST_MakePoint(2.0, 46.0), 4326), 2154))"
            )
        )
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat_l93"))


@pytest.fixture()
def info_l93(pg_incidents_l93, pg_session_factory):
    with pg_session_factory() as session:
        yield introspect_table(session, "t_feat_l93")


def test_bbox_transforms_from_crs84_to_collection_srid(info_l93, pg_session_factory):
    # La collection est en Lambert-93 (EPSG:2154) mais le bbox de la requête
    # OGC est toujours en CRS84 (lon/lat) : l'enveloppe doit être transformée
    # depuis 4326 avant comparaison, sinon elle ne matche jamais rien.
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info_l93, limit=10, offset=0, bbox=(0.5, 44.5, 1.5, 45.5))
        assert [f["id"] for f in page.features] == [1]


def test_select_is_tenant_bound_and_geojson(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=100, offset=0)
    assert page.number_matched == 2 and page.number_returned == 2
    f = page.features[0]
    assert f["type"] == "Feature" and f["id"] == 1
    assert f["geometry"] == {"type": "Point", "coordinates": [1.0, 45.0]}
    assert f["properties"] == {"titre": "a", "nb": 1}  # ni pk, ni tenant_id, ni geom


def test_pagination_and_bbox_and_filters(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=1, offset=1)
        assert page.number_matched == 2 and [f["id"] for f in page.features] == [2]
        page = select_features(session, info, limit=10, offset=0, bbox=(0.5, 44.5, 1.5, 45.5))
        assert [f["id"] for f in page.features] == [1]
        page = select_features(session, info, limit=10, offset=0, filters={"nb": "2"})
        assert [f["id"] for f in page.features] == [2]


def test_geom_intersects_filters_by_exact_polygon(info, pg_session_factory):
    polygon = {
        "type": "Polygon",
        "coordinates": [[[0.5, 44.5], [1.5, 44.5], [1.5, 45.5], [0.5, 45.5], [0.5, 44.5]]],
    }
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, geom_intersects=polygon)
        assert [f["id"] for f in page.features] == [1]


def test_geom_intersects_without_geometry_column_raises(info, pg_session_factory):
    info_no_geom = replace(info, geometry_column=None)
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(
                session,
                info_no_geom,
                limit=10,
                offset=0,
                geom_intersects={"type": "Point", "coordinates": [0, 0]},
            )


def test_filter_errors(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"inconnu": "x"})
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"nb": "pas-un-nombre"})


def test_get_feature(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        assert get_feature(session, info, fid="1")["properties"]["titre"] == "a"
        assert get_feature(session, info, fid="999") is None
        assert get_feature(session, info, fid="3") is None  # autre tenant : invisible
        assert get_feature(session, info, fid="abc") is None  # inconvertible


def test_table_extent(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        assert table_extent(session, info) == [1.0, 45.0, 2.0, 46.0]


def test_insert_stamps_current_tenant_and_returns_fid(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            fid = insert_feature(
                session,
                info,
                properties={"titre": "d", "nb": 4},
                geometry={"type": "Point", "coordinates": [4.0, 48.0]},
            )
        session.commit()
    assert isinstance(fid, int)
    with pg_session_factory() as session:
        row = session.execute(
            text("SELECT tenant_id, titre, ST_X(geom) FROM t_feat WHERE id = :i"), {"i": fid}
        ).one()
        assert row[0] == "default" and row[1] == "d" and row[2] == 4.0


def test_replace_is_full_and_scoped(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            ok = replace_feature(session, info, fid="1", properties={"titre": "a2"}, geometry=None)
            assert ok is True
            assert (
                replace_feature(
                    session,
                    info,
                    fid="3",  # autre tenant
                    properties={"titre": "hack"},
                    geometry=None,
                )
                is False
            )
            assert (
                replace_feature(session, info, fid="999", properties={"titre": "x"}, geometry=None)
                is False
            )
        session.commit()
    with pg_session_factory() as session:
        row = session.execute(text("SELECT titre, nb, geom FROM t_feat WHERE id = 1")).one()
        assert row[0] == "a2" and row[1] is None and row[2] is None  # remplacement complet
        assert (
            session.execute(text("SELECT titre FROM t_feat WHERE id = 3")).scalar() == "c"
        )  # intact


def test_delete_scoped(info, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            assert delete_feature(session, info, fid="2") is True
            assert delete_feature(session, info, fid="3") is False  # autre tenant
            assert delete_feature(session, info, fid="zzz") is False
        session.commit()
    with pg_session_factory() as session:
        assert session.execute(text("SELECT count(*) FROM t_feat")).scalar() == 2


def test_gte_lte_filters_narrow_by_range(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, filters={"nb__gte": "2"})
        assert [f["id"] for f in page.features] == [2]
        page = select_features(session, info, limit=10, offset=0, filters={"nb__lte": "1"})
        assert [f["id"] for f in page.features] == [1]
        page = select_features(
            session, info, limit=10, offset=0, filters={"nb__gte": "1", "nb__lte": "1"}
        )
        assert [f["id"] for f in page.features] == [1]


def test_in_filter_matches_any_listed_value(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, filters={"titre__in": "a,b"})
        assert sorted(f["id"] for f in page.features) == [1, 2]
        page = select_features(session, info, limit=10, offset=0, filters={"titre__in": "a"})
        assert [f["id"] for f in page.features] == [1]


def test_suffixed_filter_on_unknown_column_still_raises_filter_error(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"inconnu__gte": "1"})


def test_gte_on_unparseable_value_raises_filter_error(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"nb__gte": "pas-un-nombre"})


def test_replace_preserves_unsupported_readonly_columns(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat_ro"))
        conn.execute(
            text(
                "CREATE TABLE t_feat_ro (id serial PRIMARY KEY, titre text NOT NULL, "
                "payload jsonb NOT NULL, tenant_id text NOT NULL DEFAULT 'default', "
                "geom geometry(Point, 4326))"
            )
        )
        conn.execute(text("ALTER TABLE t_feat_ro ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation ON t_feat_ro "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_feat_ro TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_feat_ro_id_seq TO gis_rls"))
        conn.execute(
            text(
                "INSERT INTO t_feat_ro (titre, payload, tenant_id) "
                "VALUES ('a', '{\"k\": 1}', 'default')"
            )
        )
    try:
        with pg_session_factory() as session:
            info = introspect_table(session, "t_feat_ro")
            with rls_scope(session, "default"):
                ok = replace_feature(
                    session, info, fid="1", properties={"titre": "a2"}, geometry=None
                )
                assert ok is True
            session.commit()
        with pg_session_factory() as session:
            row = session.execute(text("SELECT titre, payload FROM t_feat_ro WHERE id = 1")).one()
            assert row[0] == "a2"
            assert row[1] == {"k": 1}  # la colonne read-only NOT NULL a survécu
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS t_feat_ro"))
