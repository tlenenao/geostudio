# SPDX-License-Identifier: Apache-2.0
"""REV-280e : balayage mensuel optionnel des anciennes partitions CDC."""

from io import BytesIO
from pathlib import Path

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import _dedup_cte
from app.analytics.snapshot import write_snapshot
from app.cdc import compaction, jobs
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


class _DirS3:
    """Faux client S3 adossé à un dossier : la clé `cdc/x` vit en `root/x`."""

    def __init__(self, root: Path):
        self.root = root

    def _p(self, key: str) -> Path:
        return self.root / key.removeprefix("cdc/")

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        keys = sorted(
            "cdc/" + str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()
        )
        return {
            "Contents": [
                {"Key": k, "Size": self._p(k).stat().st_size} for k in keys if k.startswith(Prefix)
            ],
            "IsTruncated": False,
        }

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": BytesIO(self._p(Key).read_bytes())}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self._p(Key).parent.mkdir(parents=True, exist_ok=True)
        self._p(Key).write_bytes(Body)

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        for o in Delete["Objects"]:
            self._p(o["Key"]).unlink()


def _put(root, dt, name, rows):
    d = root / f"tenant_id={T}" / f"collection_id={C}" / f"dt={dt}"
    d.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(d / f"{name}.parquet")


def _r(id_, nom, op="insert", lsn=1, ts=100.0):
    return {
        "id": id_,
        "nom": nom,
        "_op": op,
        "_lsn": lsn,
        "_seq": 0,
        "_ts": ts,
        "geometry": Point(id_, 0) if op != "delete" else None,
    }


def _live(conn, root):
    cte = _dedup_cte(conn, INFO, str(root), T, C)
    return conn.execute(f"{cte} SELECT id, nom, _lsn FROM live ORDER BY id").fetchall()


def test_sweep_preserves_reads_with_snapshot_and_old_partitions(tmp_path):
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    root = tmp_path / "cdc"
    for i in range(1, 5):  # 4 petits fichiers dans une vieille partition
        _put(root, "2020-01-01", f"a{i}", [_r(i, f"n{i}", lsn=i)])
    _put(
        root,
        "2020-01-02",
        "b",
        [_r(2, "n2b", "update", 10, 200.0), _r(3, None, "delete", 11, 200.0)],
    )
    write_snapshot(conn, str(root), T, C, "id", now_ms=1_000_000, grace_s=300)
    _put(root, "2020-01-03", "c", [_r(9, "n9", lsn=12, ts=900.0)])  # delta post-snapshot
    snaps = sorted((root / f"tenant_id={T}" / f"collection_id={C}" / "snapshot").iterdir())
    before = _live(conn, root)

    report = compaction.run_compaction_cycle(_DirS3(root), bucket="b", recent_days=None)

    assert report.files_removed >= 3  # la vieille partition a bien été fusionnée
    assert len(list(root.glob(f"tenant_id={T}/collection_id={C}/dt=2020-01-01/*"))) == 1
    assert sorted((root / f"tenant_id={T}" / f"collection_id={C}" / "snapshot").iterdir()) == snaps
    assert _live(conn, root) == before


@pytest.fixture()
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(jobs, "_compact", lambda recent_days: got.append(recent_days))
    return got


def test_flag_off_does_nothing(calls, monkeypatch):
    monkeypatch.delenv("CORE_CDC_COMPACTION_MONTHLY", raising=False)
    jobs.run_compaction_monthly_task(0)
    assert calls == []


def test_flag_on_sweeps_everything(calls, monkeypatch):
    monkeypatch.setenv("CORE_CDC_COMPACTION_MONTHLY", "true")
    jobs.run_compaction_monthly_task(0)
    assert calls == [None]


def test_regular_cycle_keeps_recent_window(calls, monkeypatch):
    monkeypatch.setenv("CORE_CDC_COMPACTION_RECENT_DAYS", "3")
    jobs.run_compaction_cycle_task(0)
    assert calls == [3]


def test_compaction_tasks_share_one_lock():
    """Cycle de 10 min et balayage mensuel ne compactent jamais en parallèle."""
    assert jobs.run_compaction_cycle_task.lock == "cdc_compaction"
    assert jobs.run_compaction_monthly_task.lock == "cdc_compaction"
