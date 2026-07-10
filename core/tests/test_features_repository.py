import pytest
from sqlalchemy import text

from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.features.repository import FilterError, get_feature, select_features
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_incidents(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))
        conn.execute(text(
            "CREATE TABLE t_feat (id serial PRIMARY KEY, titre text NOT NULL, "
            "nb integer, tenant_id text NOT NULL DEFAULT 'default', "
            "geom geometry(Point, 4326))"))
        conn.execute(text("ALTER TABLE t_feat ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(
            "CREATE POLICY tenant_isolation ON t_feat "
            "USING (tenant_id = current_setting('app.tenant_id')) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_feat TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_feat_id_seq TO gis_rls"))
        conn.execute(text(
            "INSERT INTO t_feat (titre, nb, tenant_id, geom) VALUES "
            "('a', 1, 'default', ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326)), "
            "('b', 2, 'default', ST_SetSRID(ST_MakePoint(2.0, 46.0), 4326)), "
            "('c', 3, 'other',   ST_SetSRID(ST_MakePoint(3.0, 47.0), 4326))"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_feat"))


@pytest.fixture()
def info(pg_incidents, pg_session_factory):
    with pg_session_factory() as session:
        yield introspect_table(session, "t_feat")


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
        page = select_features(session, info, limit=10, offset=0,
                               bbox=(0.5, 44.5, 1.5, 45.5))
        assert [f["id"] for f in page.features] == [1]
        page = select_features(session, info, limit=10, offset=0, filters={"nb": "2"})
        assert [f["id"] for f in page.features] == [2]


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
