# SPDX-License-Identifier: Apache-2.0
"""Snapshot d'état courant du lac (REV-280a) : DuckDB local sur tmp_path."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.snapshot import latest_snapshot, list_snapshots, write_snapshot

T, C = "t1", "villes"


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
        "geometry": Point(id_, id_) if op != "delete" else None,
    }


def _state(conn, uri):
    return conn.execute(f"SELECT id, nom, _op FROM read_parquet('{uri}') ORDER BY id").fetchall()


def test_snapshot_is_current_state_keeping_tombstones(tmp_path, conn):
    _put(tmp_path, "2026-01-01", "a", [_r(1, "a"), _r(2, "b"), _r(3, "c")])
    _put(
        tmp_path,
        "2026-01-02",
        "b",
        [_r(2, "b2", "update", 5, 200.0), _r(3, None, "delete", 6, 200.0)],
    )
    uri = write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000, grace_s=300)
    assert uri is not None and uri.endswith("snap-700000-6.parquet")
    assert _state(conn, uri) == [(1, "a", "insert"), (2, "b2", "update"), (3, None, "delete")]
    assert latest_snapshot(conn, str(tmp_path), T, C) == (uri, 700_000)


def test_second_snapshot_is_previous_plus_delta(tmp_path, conn):
    _put(tmp_path, "2026-01-01", "a", [_r(1, "a"), _r(2, "b")])
    first = write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000, grace_s=300)
    assert write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000, grace_s=300) is None
    _put(
        tmp_path, "2026-01-02", "b", [_r(1, "a2", "update", 9, 800.0), _r(4, "d", lsn=10, ts=800.0)]
    )
    _put(tmp_path, "2026-01-02", "late", [_r(9, "z", lsn=11, ts=2000.0)])  # après le cut : exclu
    second = write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_500_000, grace_s=300)
    assert second and second != first
    assert _state(conn, second) == [(1, "a2", "update"), (2, "b", "insert"), (4, "d", "insert")]
    assert [s[1] for s in list_snapshots(conn, str(tmp_path), T, C)] == [1_200_000, 700_000]


def test_geoparquet_roundtrip_and_no_partition_column_collision(tmp_path, conn):
    _put(tmp_path, "2026-01-01", "a", [_r(1, "a"), _r(2, "b", lsn=2)])
    uri = write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000)
    gdf = gpd.read_parquet(uri)
    assert gdf.crs.to_epsg() == 4326 and list(gdf.geometry.geom_type) == ["Point", "Point"]
    assert not {"tenant_id", "collection_id", "dt"} & set(gdf.columns)
    cols = {
        d[0]: d[1]
        for d in conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{uri}', hive_partitioning=true)"
        ).fetchall()
    }
    assert cols["tenant_id"] == "VARCHAR" and cols["collection_id"] == "VARCHAR"
    assert cols["geometry"].startswith("GEOMETRY")


def test_empty_lake_returns_none(tmp_path, conn):
    assert write_snapshot(conn, str(tmp_path), T, C, "id", now_ms=1_000_000) is None


def test_recent_partition_listing_skips_snapshot_dir(monkeypatch):
    from app.cdc import compaction

    prefixes = {
        "cdc/": ["cdc/tenant_id=t/"],
        "cdc/tenant_id=t/": ["cdc/tenant_id=t/collection_id=c/"],
        "cdc/tenant_id=t/collection_id=c/": [
            "cdc/tenant_id=t/collection_id=c/snapshot/",
            "cdc/tenant_id=t/collection_id=c/dt=2999-01-01/",
        ],
    }
    listed = []
    monkeypatch.setattr(
        compaction.storage, "list_prefixes", lambda c, *, bucket, prefix: prefixes[prefix]
    )
    monkeypatch.setattr(
        compaction.storage, "list_objects", lambda c, *, bucket, prefix: listed.append(prefix) or []
    )
    compaction.list_recent_partition_objects(None, bucket="b", recent_days=7)
    assert listed == ["cdc/tenant_id=t/collection_id=c/dt=2999-01-01/"]
