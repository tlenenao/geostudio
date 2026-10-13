# SPDX-License-Identifier: Apache-2.0
"""ARC-22 : binning carré/hexagonal des tuiles. Propriété testée (pas une durée,
piège n°7) : sur un zoom entier, la somme des comptes de toutes les tuiles vaut
`count(*)` (chaque point dans exactement une cellule, chaque cellule dans exactement
une tuile), et sum/avg recoupent un calcul direct."""

import dataclasses
import random

import pytest
from sqlalchemy import text

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.tiles import (
    MAX_TILE_FEATURES,
    MVT_BUFFER,
    MVT_EXTENT,
    bin_cell_size,
    build_bin_mvt_sql,
)

pytestmark = pytest.mark.postgis

INFO = TableInfo(
    table_name="bin_pts",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="id", type="integer", required=False),
        ColumnInfo(name="pop", type="number", required=False),
    ],
)
GENERIC = dataclasses.replace(INFO, geometry_type="MultiPoint")
MVT_TAIL = "SELECT ST_AsMVT(q, :layer, :extent, 'geom') FROM q WHERE q.geom IS NOT NULL"
N = MAX_TILE_FEATURES + 1500  # plus dense que le plafond d'une tuile brute


def _q(n):
    return f'"{n}"'


@pytest.fixture()
def conn(pg_engine):
    with pg_engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS bin_pts"))
        c.execute(
            text(
                "CREATE TABLE bin_pts (id serial PRIMARY KEY, pop double precision, "
                "geom geometry(Point, 4326))"
            )
        )
        rnd = random.Random(22)
        rows = [
            {"x": rnd.uniform(-179, 179), "y": rnd.uniform(-80, 80), "p": rnd.randint(1, 9)}
            for _ in range(N)
        ]
        # points sur des frontières de tuile et d'hexagone potentielles
        rows += [{"x": 0, "y": 0, "p": 1}, {"x": -90, "y": 0, "p": 1}, {"x": 90, "y": 45, "p": 2}]
        c.execute(
            text(
                "INSERT INTO bin_pts (pop, geom) "
                "VALUES (:p, ST_SetSRID(ST_MakePoint(:x, :y), 4326))"
            ),
            rows,
        )
        yield c
        c.execute(text("DROP TABLE IF EXISTS bin_pts"))


def _totals(conn, info, shape, stat, field, z, bins=16):
    sql = build_bin_mvt_sql(_q, info, None, shape, stat, field)
    assert MVT_TAIL in sql
    sql = sql.replace(MVT_TAIL, "SELECT point_count, value FROM q WHERE geom IS NOT NULL")
    n = 1 << z
    total_count, total_value, cells = 0, 0.0, 0
    for x in range(n):
        for y in range(n):
            params = {
                "z": z, "x": x, "y": y, "layer": "l", "extent": MVT_EXTENT,
                "buffer": MVT_BUFFER, "srid": 4326, "cell": bin_cell_size(z, bins),
            }  # fmt: skip
            for cnt, value in conn.execute(text(sql), params):
                total_count += cnt
                total_value += value
                cells += 1
    return total_count, total_value, cells


@pytest.mark.parametrize("info", [INFO, GENERIC], ids=["points4326", "generique"])
@pytest.mark.parametrize("shape", ["square", "hex"])
def test_counts_are_exact_against_count_star(conn, info, shape):
    expected = conn.execute(text("SELECT count(*) FROM bin_pts")).scalar()
    assert expected > MAX_TILE_FEATURES  # le binning couvre bien plus que le plafond brut
    count, value, cells = _totals(conn, info, shape, "count", None, z=2)
    assert count == expected
    assert value == expected  # stat count : value == point_count
    assert 10 < cells < expected


@pytest.mark.parametrize("shape", ["square", "hex"])
def test_sum_and_avg_match_direct_aggregate(conn, shape):
    total_pop = conn.execute(text("SELECT sum(pop) FROM bin_pts")).scalar()
    _, sum_value, _ = _totals(conn, INFO, shape, "sum", "pop", z=2)
    assert sum_value == pytest.approx(total_pop)
    # avg : moyenne pondérée par les comptes == moyenne globale
    sql = build_bin_mvt_sql(_q, INFO, None, shape, "avg", "pop").replace(
        MVT_TAIL, "SELECT point_count, value FROM q WHERE geom IS NOT NULL"
    )
    weighted = count = 0.0
    for x in range(4):
        for y in range(4):
            params = {
                "z": 2, "x": x, "y": y, "layer": "l", "extent": MVT_EXTENT,
                "buffer": MVT_BUFFER, "srid": 4326, "cell": bin_cell_size(2, 16),
            }  # fmt: skip
            for cnt, avg in conn.execute(text(sql), params):
                weighted += cnt * avg
                count += cnt
    assert weighted / count == pytest.approx(
        total_pop / conn.execute(text("SELECT count(*) FROM bin_pts")).scalar()
    )
