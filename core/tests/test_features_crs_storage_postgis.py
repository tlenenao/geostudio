# SPDX-License-Identifier: Apache-2.0
"""AUD-020 : collection stockée en EPSG:2154, GeoJSON toujours en lon/lat (RFC 7946)."""

import json

import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
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


def test_bulk_update_via_collection_writer_reprojects(pg_engine, pg_session_factory, table):
    from app.pipelines.collection_writer import _update_stmt

    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
            stmt = _update_stmt(s, info, [], True)
            geom = {"type": "Point", "coordinates": [5.0, 45.0]}
            s.execute(
                stmt,
                {"rows": json.dumps([{"__pk": fid, "__g": json.dumps(geom)}]), "__srid": 2154},
            )
        s.commit()
    x, y = _stored_lonlat(pg_engine, fid)
    assert (round(x, 4), round(y, 4)) == (5.0, 45.0)
    with pg_engine.begin() as conn:
        assert (
            conn.execute(text(f"SELECT ST_X(geom) FROM {T} WHERE id = :i"), {"i": fid}).scalar()
            > 600000
        )


G = "t_aud020_geolim"
LIMIT = {"type": "Polygon", "coordinates": [[[0, 40], [10, 40], [10, 50], [0, 50], [0, 40]]]}


def _blob_wkt(n: int = 60) -> str:
    """Polygone à n sommets (coordonnées à 9+ décimales), à cheval sur la limite x = 10."""
    import math

    pts = [
        (
            10 + 4.123456789012 * math.cos(2 * math.pi * i / n),
            45 + 3.987654321098 * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]
    pts.append(pts[0])
    return "POLYGON((" + ", ".join(f"{x!r} {y!r}" for x, y in pts) + "))"


@pytest.fixture()
def straddler(pg_engine, pg_session_factory):
    """Entité à cheval stockée en 2154 ; fournit (session, info, fid, version découpée relue)."""
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {G}"))
        conn.execute(
            text(
                f"CREATE TABLE {G} (id serial PRIMARY KEY, name text, geom geometry(Polygon, 2154))"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {G} (name, geom) VALUES ('s', "
                "ST_Transform(ST_GeomFromText(:w, 4326), 2154))"
            ),
            {"w": _blob_wkt()},
        )
    try:
        with pg_session_factory() as s:
            apply_collection_ddl(s, G, tenant_id="default")
            s.commit()
            info = introspect_table(s, G)
            fid = str(s.execute(text(f"SELECT id FROM {G}")).scalar())
            with rls_scope(s, "default", geo_limits={G: [LIMIT]}):
                clipped = repo.get_feature(s, info, fid=fid)["geometry"]
                yield s, info, fid, clipped
            s.rollback()
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {G}"))


def _shift_vertex(geom: dict, dlat: float) -> dict:
    g = json.loads(json.dumps(geom))
    g["coordinates"][0][3][1] += dlat
    return g


def test_straddle_gate_accepts_geojson_roundtrip_of_many_vertices(straddler):
    """60 sommets : un aller-retour GeoJSON (9 décimales) ne doit pas être refusé à tort."""
    s, info, fid, clipped = straddler
    assert len(clipped["coordinates"][0]) > 30
    assert repo.replace_feature(s, info, fid=fid, properties={"name": "ok"}, geometry=clipped)


@pytest.mark.parametrize("dlat", [1e-5, 2.5e-7])  # ~1.1 m, et ~2.8 cm (> tolérance de 1 cm)
def test_straddle_gate_refuses_a_really_different_geometry(straddler, dlat):
    from app.sharing.geo_limits import GeoLimitStraddling

    s, info, fid, clipped = straddler
    with pytest.raises(GeoLimitStraddling):
        repo.replace_feature(s, info, fid=fid, properties={}, geometry=_shift_vertex(clipped, dlat))


def test_straddle_gate_refuses_another_geometry_type(straddler):
    from app.sharing.geo_limits import GeoLimitStraddling

    s, info, fid, _ = straddler
    with pytest.raises(GeoLimitStraddling):
        repo.replace_feature(
            s, info, fid=fid, properties={}, geometry={"type": "Point", "coordinates": [6.0, 46.0]}
        )
