# SPDX-License-Identifier: Apache-2.0
"""AUD-020 : collection stockée en EPSG:2154, GeoJSON toujours en lon/lat (RFC 7946)."""

import pytest
from sqlalchemy import text

from app.collections.introspection_pg import introspect_table
from app.features import repository as repo
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis

T = "t_aud020_l93"
PARIS = {"type": "Point", "coordinates": [2.3522, 48.8566]}


@pytest.fixture()
def table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {T}"))
        conn.execute(
            text(
                f"CREATE TABLE {T} (id serial PRIMARY KEY, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 2154))"
            )
        )
        conn.execute(text(f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                f"CREATE POLICY tenant_isolation ON {T} "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE ON {T} TO gis_rls"))
        conn.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {T}_id_seq TO gis_rls"))
    yield T
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {T}"))


def _stored_lonlat(pg_engine, fid):
    with pg_engine.begin() as conn:
        return conn.execute(
            text(
                f"SELECT ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326)) "
                f"FROM {T} WHERE id = :i"
            ),
            {"i": fid},
        ).one()


def test_insert_reprojects_lonlat_to_storage_srid(pg_engine, pg_session_factory, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        assert info.srid == 2154
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
        s.commit()
    x, y = _stored_lonlat(pg_engine, fid)
    assert (round(x, 4), round(y, 4)) == (2.3522, 48.8566)


def test_insert_features_and_replace_reproject(pg_engine, pg_session_factory, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            repo.insert_features(s, info, [({}, PARIS)])
            fid = s.execute(text(f"SELECT max(id) FROM {T}")).scalar()
            repo.replace_feature(
                s,
                info,
                fid=str(fid),
                properties={},
                geometry={"type": "Point", "coordinates": [5.0, 45.0]},
            )
        s.commit()
    x, y = _stored_lonlat(pg_engine, fid)
    assert (round(x, 4), round(y, 4)) == (5.0, 45.0)


def test_default_read_is_lonlat_and_explicit_crs_is_storage(pg_session_factory, pg_engine, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
            default = repo.get_feature(s, info, fid=str(fid))
            l93 = repo.get_feature(s, info, fid=str(fid), out_srid=2154)
        s.commit()
    lon, lat = default["geometry"]["coordinates"]
    assert (round(lon, 4), round(lat, 4)) == (2.3522, 48.8566)
    assert l93["geometry"]["coordinates"][0] > 600000  # crs explicite = stockage, inchangé


def test_collection_writer_snapshot_is_lonlat(pg_engine, pg_session_factory, table):
    from app.pipelines.collection_writer import _snapshots

    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
        s.commit()
        snap = _snapshots(s, info, "default", [fid])
    lon, lat = snap[fid]["geometry"]["coordinates"]
    assert (round(lon, 4), round(lat, 4)) == (2.3522, 48.8566)
