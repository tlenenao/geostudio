# SPDX-License-Identifier: Apache-2.0
"""Lecture du lac via snapshot (REV-280a) : doit être IDENTIQUE à la lecture
des partitions brutes (équivalence), tombstones et backfill tardif inclus."""

import shutil

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import (
    AggregateRequestBody,
    _dedup_cte,
    lake_as_of,
    run_collection_aggregate,
)
from app.analytics.snapshot import snapshot_dir, write_snapshot
from app.analytics.sql_sandbox import run_analyst_sql
from app.collections.introspection import ColumnInfo, TableInfo

T, C = "t1", "villes"
INFO = TableInfo(
    table_name=C,
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="nom", type="string", required=True)],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _put(base, dt, name, rows):
    d = base / f"tenant_id={T}" / f"collection_id={C}" / f"dt={dt}"
    d.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(d / f"{name}.parquet")


def _r(id_, nom, op="insert", lsn=1, ts=100.0, seq=0):
    return {
        "id": id_,
        "nom": nom,
        "_op": op,
        "_lsn": lsn,
        "_seq": seq,
        "_ts": ts,
        "geometry": Point(id_, 0) if op != "delete" else None,
    }


def _live(conn, base):
    cte = _dedup_cte(conn, INFO, str(base), T, C)
    return conn.execute(
        f"{cte} SELECT id, nom, _lsn, ST_AsText(geom) FROM live ORDER BY id"
    ).fetchall()


def _seed(base, conn):
    """Historique : insert/update/delete/ré-insertion + backfill tardif."""
    _put(base, "d1", "a", [_r(i, f"n{i}", lsn=i, ts=100.0) for i in range(1, 7)])
    _put(
        base,
        "d2",
        "b",
        [
            _r(2, "n2b", "update", 20, 200.0),
            _r(3, None, "delete", 21, 200.0),
            _r(4, None, "delete", 22, 200.0),
            _r(4, "n4-back", "insert", 23, 201.0, seq=1),  # ré-insertion
        ],
    )
    write_snapshot(conn, str(base), T, C, "id", now_ms=1_000_000, grace_s=300)  # cut = 700 s
    # Après le snapshot : update, delete, et un backfill TARDIF (LSN basse) sur
    # une PK supprimée avant le cut (3) — la tombstone doit toujours l'emporter.
    _put(
        base,
        "d3",
        "c",
        [
            _r(1, "n1b", "update", 30, 900.0),
            _r(5, None, "delete", 31, 900.0),
            _r(7, "n7", lsn=32, ts=900.0),
        ],
    )
    _put(base, "d3", "backfill", [_r(3, "ressuscite?", lsn=5, ts=950.0)])


def test_snapshot_read_equals_raw_read(tmp_path, conn):
    _seed(tmp_path, conn)
    with_snap = _live(conn, tmp_path)
    shutil.rmtree(snapshot_dir(str(tmp_path), T, C))
    raw = _live(conn, tmp_path)
    assert with_snap == raw
    assert [r[0] for r in raw] == [1, 2, 4, 6, 7]  # 3 et 5 supprimés, 4 ré-inséré


def test_cte_really_goes_through_snapshot(tmp_path, conn):
    _seed(tmp_path, conn)
    assert "snap-700000-" in _dedup_cte(conn, INFO, str(tmp_path), T, C)


def test_aggregate_and_sandbox_see_same_view(tmp_path, conn):
    _seed(tmp_path, conn)
    req = AggregateRequestBody(groupBy="nom", agg="count")
    sql = "SELECT id, nom FROM villes ORDER BY id"

    def both():
        c = duckdb.connect(":memory:")
        c.execute("INSTALL spatial; LOAD spatial;")
        agg = run_collection_aggregate(
            c, base_uri=str(tmp_path), tenant_id=T, collection_id=C, table_info=INFO, request=req
        )
        c2 = duckdb.connect(":memory:")
        c2.execute("INSTALL spatial; LOAD spatial;")
        sb = run_analyst_sql(c2, sql=sql, allowed={C: INFO}, base_uri=str(tmp_path), tenant_id=T)
        return agg, sb

    with_snap = both()
    shutil.rmtree(snapshot_dir(str(tmp_path), T, C))
    assert both() == with_snap


def test_no_snapshot_keeps_raw_behaviour_and_as_of_ignores_snapshot(tmp_path, conn):
    _put(tmp_path, "d1", "a", [_r(1, "a", ts=100.0)])
    assert [r[0] for r in _live(conn, tmp_path)] == [1]
    write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000)
    _put(tmp_path, "d2", "b", [_r(2, "b", ts=900.0)])
    # asOf = max(_ts) des partitions brutes : un snapshot (cut 700) ne le tire pas en arrière.
    assert lake_as_of(conn, str(tmp_path), T, C).startswith("1970-01-01T00:15:00")
