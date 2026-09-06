# SPDX-License-Identifier: Apache-2.0
from io import BytesIO

import geopandas as gpd
from shapely.geometry import Point

from app.cdc.compaction import (
    CompactionReport,
    compact_partition,
    group_by_partition,
    merge_geoparquet,
    run_compaction_cycle,
    select_files_to_merge,
)


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.delete_should_fail = False

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        matching = sorted(k for k in self.objects if k.startswith(Prefix))
        return {
            "Contents": [{"Key": k, "Size": len(self.objects[k])} for k in matching],
            "IsTruncated": False,
        }

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[Key] = Body

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        if self.delete_should_fail:
            raise RuntimeError("simulated crash between upload and delete")
        for o in Delete["Objects"]:
            self.objects.pop(o["Key"], None)
            self.deleted.append(o["Key"])


def _geoparquet_bytes(rows: list[dict]) -> bytes:
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    buf = BytesIO()
    gdf.to_parquet(buf)
    return buf.getvalue()


def _read_all_current(client, keys: list[str]) -> list[tuple]:
    """Aide de test : réduction (pk, max(_lsn)) minimale, juste assez pour
    comparer un résultat de lecture avant/après compaction — la vraie
    réduction complète vit dans le module analytique (Task 6)."""
    frames = [gpd.read_parquet(BytesIO(client.objects[k])) for k in keys if k in client.objects]
    import pandas as pd

    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if all_rows.empty:
        return []
    current = all_rows.sort_values("_lsn").groupby("id").tail(1)
    current = current[current["_op"] != "delete"]
    return sorted(zip(current["id"], current["titre"], strict=True))


PARTITION = "cdc/tenant_id=t1/collection_id=c1/dt=2026-07-18/"


def test_group_by_partition_groups_files_under_the_same_prefix():
    objects = [
        {"key": f"{PARTITION}part-a.parquet", "size": 10},
        {"key": f"{PARTITION}part-b.parquet", "size": 10},
        {"key": "cdc/tenant_id=t1/collection_id=c2/dt=2026-07-18/part-c.parquet", "size": 10},
    ]
    groups = group_by_partition(objects)
    assert set(groups.keys()) == {PARTITION, "cdc/tenant_id=t1/collection_id=c2/dt=2026-07-18/"}
    assert len(groups[PARTITION]) == 2


def test_select_files_to_merge_excludes_large_files():
    files = [{"key": "a", "size": 10}, {"key": "b", "size": 10}, {"key": "big", "size": 100}]
    selected = select_files_to_merge(files, size_threshold_bytes=50)
    assert {f["key"] for f in selected} == {"a", "b"}


def test_select_files_to_merge_returns_empty_when_at_most_one_eligible():
    files = [{"key": "a", "size": 10}, {"key": "big", "size": 100}]
    assert select_files_to_merge(files, size_threshold_bytes=50) == []


def test_merge_geoparquet_concatenates_and_preserves_crs():
    blob1 = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}]
    )
    blob2 = _geoparquet_bytes(
        [{"id": 2, "titre": "b", "_op": "insert", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}]
    )
    merged = merge_geoparquet([blob1, blob2])
    gdf = gpd.read_parquet(BytesIO(merged))
    assert len(gdf) == 2
    assert gdf.crs.to_epsg() == 4326
    assert sorted(gdf["id"]) == [1, 2]


def test_compact_partition_merges_eligible_files_and_removes_originals():
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}]
    )
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}]
    )
    files = [{"key": k, "size": len(v)} for k, v in client.objects.items()]

    merged_count = compact_partition(
        client,
        bucket="b",
        partition_prefix=PARTITION,
        files=files,
        size_threshold_bytes=20000,
    )

    assert merged_count == 2
    remaining = list(client.objects.keys())
    assert len(remaining) == 1  # les 2 originaux ont disparu, remplacés par 1 fichier fusionné
    assert remaining[0].startswith(PARTITION) and remaining[0] not in {f["key"] for f in files}
    assert _read_all_current(client, remaining) == [(1, "b")]  # lsn max gagne, résultat inchangé


def test_compact_partition_skips_when_nothing_eligible():
    client = _FakeS3Client()
    big = b"x" * 100
    client.objects[f"{PARTITION}part-big.parquet"] = big
    files = [{"key": f"{PARTITION}part-big.parquet", "size": 100}]
    merged_count = compact_partition(
        client,
        bucket="b",
        partition_prefix=PARTITION,
        files=files,
        size_threshold_bytes=50,
    )
    assert merged_count == 0
    assert list(client.objects.keys()) == [f"{PARTITION}part-big.parquet"]  # non touché


def test_compact_partition_writes_merged_file_before_deleting_originals_on_crash():
    """Sûreté à l'interruption : si delete_objects crashe APRÈS l'upload
    (simulé ici), le fichier fusionné doit déjà exister aux côtés des
    originaux — jamais de perte, juste des doublons inoffensifs (réduits
    par (pk, max(_lsn)) à la lecture, Task 6)."""
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}]
    )
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 2, "titre": "b", "_op": "insert", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}]
    )
    files = [{"key": k, "size": len(v)} for k, v in client.objects.items()]
    client.delete_should_fail = True

    try:
        compact_partition(
            client, bucket="b", partition_prefix=PARTITION, files=files, size_threshold_bytes=20000
        )
    except RuntimeError:
        pass

    keys = list(client.objects.keys())
    assert len(keys) == 3  # 2 originaux + 1 fusionné : rien supprimé, rien perdu
    assert _read_all_current(client, keys) == [
        (1, "a"),
        (2, "b"),
    ]  # résultat inchangé malgré le doublon


def test_run_compaction_cycle_isolates_partition_errors_and_continues():
    """Une partition dont la fusion échoue (fichier .parquet corrompu, ex.)
    ne doit pas interrompre tout le cycle — les autres partitions doivent
    quand même être compactées, et l'échec doit être compté (REV-025)."""
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}]
    )
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}]
    )
    bad_prefix = "cdc/tenant_id=t2/collection_id=c9/dt=2026-07-18/"
    client.objects[f"{bad_prefix}part-a.parquet"] = b"not a valid geoparquet file"
    client.objects[f"{bad_prefix}part-b.parquet"] = b"not a valid geoparquet file either"

    report = run_compaction_cycle(client, bucket="b", size_threshold_bytes=20000)

    assert report.partitions_scanned == 2
    assert report.partitions_compacted == 1  # la bonne partition, malgré l'échec de l'autre
    assert report.partitions_failed == 1
    assert report.files_removed == 2
    # la partition en échec garde ses fichiers originaux intacts (rien perdu)
    assert f"{bad_prefix}part-a.parquet" in client.objects
    assert f"{bad_prefix}part-b.parquet" in client.objects


def test_run_compaction_cycle_reports_across_partitions():
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}]
    )
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}]
    )
    other_prefix = "cdc/tenant_id=t2/collection_id=c9/dt=2026-07-18/"
    client.objects[f"{other_prefix}part-only.parquet"] = b"x" * 100  # seul, jamais éligible

    report = run_compaction_cycle(client, bucket="b", size_threshold_bytes=20000)

    assert report == CompactionReport(
        partitions_scanned=2, partitions_compacted=1, files_removed=2, partitions_failed=0
    )
