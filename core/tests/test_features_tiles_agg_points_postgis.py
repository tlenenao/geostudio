# SPDX-License-Identifier: Apache-2.0
"""REV-283 (E-bis-3) : le chemin « points 4326 » de l'agrégation de tuile (grille calculée
en Mercator par formule) doit rendre les MÊMES cellules que le chemin générique
(ST_Transform par ligne). Comparaison sur un jeu fixe, pas de durée (piège n°7)."""

import dataclasses
import random

import pytest
from sqlalchemy import text

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.tiles import MVT_BUFFER, MVT_EXTENT, agg_cell_size, build_agg_mvt_sql

pytestmark = pytest.mark.postgis

Z, X, Y = 5, 16, 11
INFO = TableInfo(
    table_name="agg_pts",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="id", type="integer", required=False)],
)
GENERIC = dataclasses.replace(INFO, geometry_type="MultiPoint")
MVT_TAIL = "SELECT ST_AsMVT(q, :layer, :extent, 'geom') FROM q WHERE q.geom IS NOT NULL"


def _q(n):
    return f'"{n}"'


@pytest.fixture()
def conn(pg_engine):
    with pg_engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS agg_pts"))
        c.execute(text("CREATE TABLE agg_pts (id serial PRIMARY KEY, geom geometry(Point, 4326))"))
        rnd = random.Random(283)
        c.execute(
            text("INSERT INTO agg_pts (geom) VALUES (ST_SetSRID(ST_MakePoint(:x, :y), 4326))"),
            [{"x": rnd.uniform(-5, 9), "y": rnd.uniform(41, 51.5)} for _ in range(3000)],
        )
        yield c
        c.execute(text("DROP TABLE IF EXISTS agg_pts"))


def _cells(conn, info):
    """(count, x, y en coordonnées de tuile) de chaque cellule, avant encodage MVT."""
    sql = build_agg_mvt_sql(_q, info)
    assert MVT_TAIL in sql
    sql = sql.replace(
        MVT_TAIL,
        "SELECT point_count, ST_X(geom), ST_Y(geom) FROM q WHERE geom IS NOT NULL ORDER BY 2, 3, 1",
    )
    params = {
        "z": Z, "x": X, "y": Y, "layer": "l", "extent": MVT_EXTENT,
        "buffer": MVT_BUFFER, "srid": 4326, "cell": agg_cell_size(Z),
    }  # fmt: skip
    return conn.execute(text(sql), params).all()


def test_points_4326_path_matches_generic_path(conn):
    new, old = _cells(conn, INFO), _cells(conn, GENERIC)
    assert len(new) > 10
    assert sum(r[0] for r in new) == sum(r[0] for r in old) > 1000
    assert len(new) == len(old)
    for (cn, xn, yn), (co, xo, yo) in zip(new, old, strict=True):
        assert cn == co
        assert abs(xn - xo) <= 1 and abs(yn - yo) <= 1


def test_points_4326_path_has_no_per_row_transform():
    fast = build_agg_mvt_sql(_q, INFO)
    assert "ST_PointOnSurface" not in fast
    assert "ST_Transform(t." not in fast


@pytest.mark.parametrize(
    "geometry_type,srid",
    [("Polygon", 4326), ("MultiPolygon", 4326), ("MultiPoint", 4326), ("Point", 2154)],
)
def test_other_geometries_and_srids_keep_the_generic_path(geometry_type, srid):
    info = dataclasses.replace(INFO, geometry_type=geometry_type, srid=srid)
    assert "ST_PointOnSurface(ST_Transform(t." in build_agg_mvt_sql(_q, info)
