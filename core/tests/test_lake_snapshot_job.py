# SPDX-License-Identifier: Apache-2.0
"""Cycle périodique de snapshot du lac (REV-280a)."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.cdc import jobs


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _files(base, n, *, dt="2026-01-01", t="t1", c="villes", ts=100.0, start=0):
    d = base / f"tenant_id={t}" / f"collection_id={c}" / f"dt={dt}"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(start, start + n):
        rows = [
            {"id": i, "_op": "insert", "_lsn": i, "_seq": 0, "_ts": ts, "geometry": Point(i, 0)}
        ]
        gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(d / f"f{i}.parquet")


def _run(conn, tmp_path, monkeypatch, **kw):
    # Le cycle parle s3://bucket/cdc : on le redirige sur tmp_path (DuckDB lit pareil en local).
    monkeypatch.setattr(jobs, "_base_uri", lambda bucket: str(tmp_path))
    deleted = []
    monkeypatch.setattr(
        jobs.storage, "delete_objects", lambda client, *, bucket, keys: deleted.extend(keys)
    )
    args = dict(
        bucket="b",
        collections=[("t1", "villes", "id")],
        now_ms=1_000_000,
        min_delta_files=3,
        keep=2,
    )
    args.update(kw)
    return jobs.run_snapshot_cycle(conn, None, **args), deleted


def test_flag_off_does_nothing(monkeypatch):
    monkeypatch.delenv("CORE_LAKE_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.setattr(
        jobs, "open_connection", lambda **_: pytest.fail("ne doit pas ouvrir DuckDB")
    )
    jobs.run_snapshot_cycle_task(timestamp=0)


def test_below_threshold_writes_nothing(tmp_path, conn, monkeypatch):
    _files(tmp_path, 2)
    assert _run(conn, tmp_path, monkeypatch)[0] == 0
    assert not list(tmp_path.rglob("snap-*"))


def test_snapshot_written_then_old_ones_purged_beyond_keep(tmp_path, conn, monkeypatch):
    _files(tmp_path, 3)
    assert _run(conn, tmp_path, monkeypatch)[0] == 1
    _files(tmp_path, 3, start=10, ts=800.0)
    assert _run(conn, tmp_path, monkeypatch, now_ms=1_500_000)[0] == 1
    _files(tmp_path, 3, start=20, ts=1300.0)
    written, deleted = _run(conn, tmp_path, monkeypatch, now_ms=2_000_000)
    assert written == 1
    assert len(deleted) == 1 and "snap-700000-" in deleted[0]  # le plus ancien, au-delà de keep=2


def test_failure_on_one_collection_does_not_stop_the_next(tmp_path, conn, monkeypatch):
    _files(tmp_path, 3, c="ok")
    calls = []
    real = jobs.write_snapshot

    def flaky(conn, base, t, c, pk, **kw):
        calls.append(c)
        if c == "bad":
            raise RuntimeError("boom")
        return real(conn, base, t, c, pk, **kw)

    monkeypatch.setattr(jobs, "write_snapshot", flaky)
    _files(tmp_path, 3, c="bad")
    n, _ = _run(conn, tmp_path, monkeypatch, collections=[("t1", "bad", "id"), ("t1", "ok", "id")])
    assert n == 1 and calls == ["bad", "ok"]


def test_keep_floor_is_two(monkeypatch):
    test_task_wires_env_collections_and_thresholds(monkeypatch, keep="1", expect=2)


def test_task_wires_env_collections_and_thresholds(monkeypatch, keep="3", expect=3):
    from contextlib import contextmanager
    from types import SimpleNamespace

    for k, v in {
        "CORE_LAKE_SNAPSHOT_ENABLED": "true",
        "CORE_LAKE_SNAPSHOT_MIN_DELTA_FILES": "7",
        "CORE_LAKE_SNAPSHOT_KEEP": keep,
        "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_ACCESS_KEY": "ak",
        "S3_SECRET_KEY": "sk",
        "S3_CDC_BUCKET": "bk",
    }.items():
        monkeypatch.setenv(k, v)
    col = SimpleNamespace(tenant_id="t", id="c", pk_column="pk")

    @contextmanager
    def fake_session(_factory):
        yield SimpleNamespace(execute=lambda _q: SimpleNamespace(scalars=lambda: [col]))

    seen = {}
    monkeypatch.setattr(jobs, "request_scoped_session", fake_session)
    monkeypatch.setattr(jobs, "session_factory", lambda: None)
    monkeypatch.setattr(jobs.storage, "make_s3_client", lambda **_: "client")
    monkeypatch.setattr(jobs, "open_connection", lambda **_: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(jobs, "run_snapshot_cycle", lambda conn, client, **kw: seen.update(kw) or 0)
    jobs.run_snapshot_cycle_task(timestamp=0)
    assert seen["collections"] == [("t", "c", "pk")]
    assert (seen["bucket"], seen["min_delta_files"], seen["keep"]) == ("bk", 7, expect)


def test_purge_passes_exact_s3_keys_and_cleanup_deletes_final_key(monkeypatch):
    from unittest.mock import MagicMock

    snaps = [
        (f"s3://bk/cdc/tenant_id=t/collection_id=c/snapshot/snap-{i}-1.parquet", i, 1)
        for i in (3, 2, 1)
    ]
    monkeypatch.setattr(jobs, "_delta_file_count", lambda *a: 99)
    monkeypatch.setattr(jobs, "list_snapshots", lambda *a: snaps)
    seen = {}

    def fake_write(conn, base, t, c, pk, *, now_ms, cleanup):
        seen["cleanup"] = cleanup
        return snaps[0][0]

    monkeypatch.setattr(jobs, "write_snapshot", fake_write)
    client = MagicMock()
    jobs.run_snapshot_cycle(
        MagicMock(), client, bucket="bk", collections=[("t", "c", "id")],
        now_ms=1, min_delta_files=1, keep=2,
    )  # fmt: skip
    client.delete_objects.assert_called_once_with(
        Bucket="bk",
        Delete={"Objects": [{"Key": "cdc/tenant_id=t/collection_id=c/snapshot/snap-1-1.parquet"}]},
    )
    client.reset_mock()
    seen["cleanup"](snaps[0][0])
    client.delete_objects.assert_called_once_with(
        Bucket="bk",
        Delete={"Objects": [{"Key": "cdc/tenant_id=t/collection_id=c/snapshot/snap-3-1.parquet"}]},
    )


def test_task_is_serialized():
    assert jobs.run_snapshot_cycle_task.lock == "run_snapshot_cycle"
