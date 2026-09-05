# SPDX-License-Identifier: Apache-2.0
"""Tests SANS MinIO réel : DuckDB lit des chemins LOCAUX (tmp_path) exactement
comme il lirait s3:// (même read_parquet/glob, DuckDB dispatche sur le schéma
du chemin) — seule la connectivité réseau réelle est hors du périmètre de ces
tests (prouvée par le spike Task 1 + le script empirique Task 10)."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import (
    AggregateMeasure,
    AggregateRequestBody,
    UnknownAggregateField,
    run_collection_aggregate,
)
from app.collections.introspection import ColumnInfo, TableInfo

TABLE_INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="annee", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")  # bbox, pas de httpfs (chemins locaux)
    return c


def _write_partition(base_dir, *, tenant_id="t1", collection_id="villes", rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _row(id_, region, annee, pop, *, op="insert", lsn=1, seq=0, x=0.0, y=0.0):
    return {
        "id": id_,
        "region": region,
        "annee": annee,
        "pop": pop,
        "_op": op,
        "_lsn": lsn,
        "_seq": seq,
        "_ts": 1.0,
        "geometry": Point(x, y),
    }


def test_group_by_with_split_produces_wide_rows_matching_client_contract(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2026", 12, lsn=1),
            _row(3, "Sud", "2025", 5, lsn=1),
            _row(4, "Sud", "2026", 7, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", split="annee", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "region"
    by_region = {r["region"]: r for r in rows}
    assert by_region["Nord"] == {"region": "Nord", "2025": 10, "2026": 12}
    assert by_region["Sud"] == {"region": "Sud", "2025": 5, "2026": 7}


def test_group_by_without_split_uses_single_measure_labeled_value(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Sud", "2025", 5, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "region"
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10},
        {"region": "Sud", "value": 5},
    ]


def test_multiple_measures_use_their_own_labels(tmp_path, conn):
    _write_partition(
        tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)]
    )
    request = AggregateRequestBody(
        groupBy="region",
        measures=[
            AggregateMeasure(agg="sum", field="pop", label="total"),
            AggregateMeasure(agg="count", label="nb"),
        ],
    )

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "total": 30, "nb": 2}]


def test_no_group_by_produces_a_single_total_row(tmp_path, conn):
    _write_partition(
        tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)]
    )
    request = AggregateRequestBody(agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "group"
    assert rows == [{"group": "Total", "value": 15}]


def test_reduces_to_current_state_last_lsn_wins_and_tombstone_excluded(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(1, "Nord", "2025", 999, lsn=5),  # update : doit gagner
            _row(2, "Sud", "2025", 5, lsn=1),
            _row(2, "Sud", "2025", 0, lsn=2, op="delete"),  # tombstone : doit disparaître
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 999}]  # Sud entièrement supprimé


def test_tie_on_same_lsn_keeps_the_later_added_row_not_the_first_seen(tmp_path, conn):
    """core/app/cdc/consumer.py:54-70 documente que deux transactions
    distinctes captées dans la même fenêtre de settle CDC peuvent partager
    exactement la même valeur `_lsn` — c'est alors l'ORDRE D'AJOUT (`_seq`),
    pas `_lsn`, qui doit départager la ligne la plus récente. "Nord" (msg,
    ajoutée en premier) doit perdre face à "Nord" (extra, même _lsn, ajoutée
    après)."""
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=5, seq=1),  # "msg" : ajoutée en premier
            _row(1, "Nord", "2025", 999, lsn=5, seq=2),  # "extra" : même _lsn, ajoutée après
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 999}]


def test_attribute_filter_narrows_rows(tmp_path, conn):
    _write_partition(
        tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)]
    )
    request = AggregateRequestBody(
        groupBy="region", agg="sum", field="pop", filters={"region": "Nord"}
    )

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_bbox_filter_narrows_rows_spatially(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1, x=2.3, y=48.8),  # dans le bbox
            _row(2, "Sud", "2025", 5, lsn=1, x=100.0, y=50.0),  # hors bbox
        ],
    )
    request = AggregateRequestBody(
        groupBy="region", agg="sum", field="pop", bbox=(2.0, 48.0, 3.0, 49.0)
    )

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_empty_collection_returns_empty_rows_without_error(tmp_path, conn):
    # Aucune partition écrite du tout — même chemin que "collection jamais flushée".
    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=AggregateRequestBody(groupBy="region"),
    )
    assert category_key == "region"
    assert rows == []


def test_unknown_group_by_field_raises_with_field_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="inconnu")
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc_info.value.field == "groupBy"


def test_bbox_without_geometry_column_raises():
    info_no_geom = TableInfo(
        table_name="t",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
        columns=[],
    )
    request = AggregateRequestBody(bbox=(0, 0, 1, 1))
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            duckdb.connect(":memory:"),
            base_uri="/nonexistent",
            tenant_id="t1",
            collection_id="c",
            table_info=info_no_geom,
            request=request,
        )
    assert exc_info.value.field == "bbox"


def test_geom_intersects_filter_narrows_rows_spatially(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1, x=2.3, y=48.8),  # dans le polygone
            _row(2, "Sud", "2025", 5, lsn=1, x=100.0, y=50.0),  # hors polygone
        ],
    )
    polygon = {
        "type": "Polygon",
        "coordinates": [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]],
    }
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", geomIntersects=polygon)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_geom_intersects_without_geometry_column_raises():
    info_no_geom = TableInfo(
        table_name="t",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
        columns=[],
    )
    request = AggregateRequestBody(geomIntersects={"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            duckdb.connect(":memory:"),
            base_uri="/nonexistent",
            tenant_id="t1",
            collection_id="c",
            table_info=info_no_geom,
            request=request,
        )
    assert exc_info.value.field == "geomIntersects"


def test_gte_lte_filters_narrow_rows(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2026", 20, lsn=1),
            _row(3, "Sud", "2025", 5, lsn=1),
        ],
    )
    request = AggregateRequestBody(
        groupBy="region", agg="sum", field="pop", filters={"annee__gte": "2026"}
    )
    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )
    assert rows == [{"region": "Nord", "value": 20}]


def test_in_filter_matches_any_listed_value(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Sud", "2025", 5, lsn=1),
            _row(3, "Est", "2025", 3, lsn=1),
        ],
    )
    request = AggregateRequestBody(
        groupBy="region", agg="sum", field="pop", filters={"region__in": "Nord,Sud"}
    )
    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10},
        {"region": "Sud", "value": 5},
    ]


def test_suffixed_filter_on_unknown_field_raises_with_stripped_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", filters={"inconnu__gte": "1"})
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert "inconnu" in str(exc_info.value)


def test_bucket_groups_rows_by_day(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05", 10, lsn=1),
            _row(2, "Sud", "2026-01-05", 3, lsn=1),
            _row(3, "Nord", "2026-01-06", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="count")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "annee"
    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 00:00:00", "value": 2},
        {"annee": "2026-01-06 00:00:00", "value": 1},
    ]


def test_bucket_normalizes_timestamptz_offset_before_truncating(tmp_path, conn):
    """Deux lignes représentant EXACTEMENT le même instant réel (23:30 UTC le
    5 janvier 2026), écrites avec deux offsets différents comme le ferait le
    CDC (backfill._pg_timestamp_str / wal2json), doivent tomber dans le MÊME
    bucket 'day' — un TRY_CAST(... AS TIMESTAMP) nu jetterait silencieusement
    l'offset et les séparerait en deux buckets distincts."""
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05 23:30:00+00", 1, lsn=1),
            _row(2, "Sud", "2026-01-06 01:30:00+02", 1, lsn=1),  # même instant, 23:30 UTC
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="count")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "annee"
    assert rows == [{"annee": "2026-01-05 00:00:00", "value": 2}]


def test_bucket_groups_rows_by_month(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05", 10, lsn=1),
            _row(2, "Nord", "2026-01-20", 5, lsn=1),
            _row(3, "Nord", "2026-02-10", 7, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="month", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-01 00:00:00", "value": 15},
        {"annee": "2026-02-01 00:00:00", "value": 7},
    ]


def test_bucket_without_group_by_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2026-01-05", 10, lsn=1)])
    request = AggregateRequestBody(bucket="day")

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "bucket"


def test_bucket_on_non_castable_field_groups_under_a_null_bucket(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "pas-une-date", 10, lsn=1),
            _row(2, "Sud", "2026-01-05", 3, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    by_key = {r["annee"]: r["value"] for r in rows}
    assert by_key["None"] == 10
    assert by_key["2026-01-05 00:00:00"] == 3


def test_groupby_list_with_duplicate_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "region"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "groupBy"


def test_bucket_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], bucket="day")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "bucket"


def test_split_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], split="annee")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "split"


def test_groupby_list_with_unknown_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "inconnu"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "groupBy"


def test_two_field_groupby_produces_tidy_rows(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2026", 12, lsn=1),
            _row(3, "Sud", "2025", 5, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy=["region", "annee"], agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == ["region", "annee"]
    assert sorted(rows, key=lambda r: (r["region"], r["annee"])) == [
        {"region": "Nord", "annee": "2025", "value": 10},
        {"region": "Nord", "annee": "2026", "value": 12},
        {"region": "Sud", "annee": "2025", "value": 5},
    ]


def test_three_field_groupby_produces_tidy_rows(tmp_path, conn):
    # Réutilise "pop" comme 3e dimension (valeurs distinctes = niveau de hiérarchie),
    # TABLE_INFO n'a que 3 colonnes non-géométrie disponibles pour ce test.
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy=["region", "annee", "pop"], agg="count")

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == ["region", "annee", "pop"]
    assert sorted(rows, key=lambda r: r["pop"]) == [
        {"region": "Nord", "annee": "2025", "pop": 10, "value": 1},
        {"region": "Nord", "annee": "2025", "pop": 20, "value": 1},
    ]


def test_multi_field_groupby_with_multiple_measures(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
            _row(3, "Sud", "2025", 5, lsn=1),
        ],
    )
    request = AggregateRequestBody(
        groupBy=["region", "annee"],
        measures=[
            AggregateMeasure(agg="sum", field="pop", label="total"),
            AggregateMeasure(agg="count", label="nb"),
        ],
    )

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "annee": "2025", "total": 30, "nb": 2},
        {"region": "Sud", "annee": "2025", "total": 5, "nb": 1},
    ]


def test_bins_produces_equal_width_buckets(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 1, lsn=1),
            _row(2, "Nord", "2025", 2, lsn=1),
            _row(3, "Nord", "2025", 9, lsn=1),
            _row(4, "Nord", "2025", 10, lsn=1),
        ],
    )
    request = AggregateRequestBody(field="pop", bins=3)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # pop in [1, 10], 3 bins of width 3 → [1,4), [4,7), [7,10]
    # (last bin absorbs the max via LEAST clamp)
    by_index = {r["bucketIndex"]: r["count"] for r in rows}
    assert by_index == {
        0: 2,
        2: 2,
    }  # pop 1,2 → bin 0 ; pop 9,10 → bin 2 (clamped) ; bin 1 empty, absent


def test_bins_on_a_constant_field_returns_one_bucket(tmp_path, conn):
    _write_partition(
        tmp_path, rows=[_row(1, "Nord", "2025", 5, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)]
    )
    request = AggregateRequestBody(field="pop", bins=4)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 5.0, "bucketEnd": 5.0, "count": 2}]


def test_bins_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "bins"


def test_bins_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "bins"


def test_bins_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 101):
        request = AggregateRequestBody(field="pop", bins=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="villes",
                table_info=TABLE_INFO,
                request=request,
            )
        assert exc.value.field == "bins"


def test_bins_narrowed_by_attribute_filter(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 1, lsn=1),
            _row(2, "Sud", "2025", 9, lsn=1),
        ],
    )
    request = AggregateRequestBody(field="pop", bins=2, filters={"region": "Nord"})

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 1.0, "bucketEnd": 1.0, "count": 1}]


def test_bins_excludes_non_numeric_values_from_top_bucket(tmp_path, conn):
    """Regression test: non-numeric strings should be filtered out by TRY_CAST,
    not silently miscounted into the top bucket by DuckDB's NULL-ignoring LEAST."""
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", "1", lsn=1),  # numeric string
            _row(2, "Nord", "2025", "2", lsn=1),  # numeric string
            _row(3, "Nord", "2025", "abc", lsn=1),  # non-numeric string → TRY_CAST → NULL
            _row(4, "Nord", "2025", "10", lsn=1),  # numeric string (max)
        ],
    )
    request = AggregateRequestBody(field="pop", bins=3)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # After TRY_CAST("1"/"2"/"abc"/"10" AS DOUBLE): 1.0, 2.0, NULL, 10.0
    # lo=1.0, hi=10.0, width=3.0
    # Bucket 0: [1, 4) contains 1.0, 2.0 → count=2
    # Bucket 2: [7, 10] contains 10.0 → count=1
    # "abc" should NOT appear in any bucket; total count must be 3, not 4
    by_index = {r["bucketIndex"]: r["count"] for r in rows}
    assert by_index == {0: 2, 2: 1}, f"Expected {{0: 2, 2: 1}}, got {by_index}"
    total_count = sum(r["count"] for r in rows)
    assert total_count == 3, (
        f"Expected total count 3, got {total_count} (non-numeric 'abc' was not excluded)"
    )


def test_count_distinct_counts_distinct_text_values(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
            _row(3, "Nord", "2026", 30, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="countDistinct", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 2}]


def test_median_returns_the_middle_value(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10, lsn=1),
            _row(2, "Nord", "2025", 20, lsn=1),
            _row(3, "Nord", "2025", 60, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="median", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 20}]


def test_percentile_uses_p_as_a_percentage(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i * 10, lsn=1) for i in range(1, 11)],
    )
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop", p=90)

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows[0]["region"] == "Nord"
    assert rows[0]["value"] == pytest.approx(91.0, abs=1e-6)


def test_stddev_is_the_sample_standard_deviation(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 2, lsn=1),
            _row(2, "Nord", "2025", 4, lsn=1),
            _row(3, "Nord", "2025", 4, lsn=1),
            _row(4, "Nord", "2025", 6, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="region", agg="stddev", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # STDDEV_SAMP (n-1) de [2,4,4,6] = 1.632…, là où STDDEV_POP donnerait 1.414.
    assert rows[0]["value"] == pytest.approx(1.632993, abs=1e-5)


def test_stddev_of_a_single_row_group_is_null_not_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="stddev", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": None}]


def test_median_of_a_group_without_castable_values_is_null_not_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "pas-un-nombre", None, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="median", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": None}]


@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max"])
def test_agg_of_a_group_without_castable_values_is_null_not_zero(tmp_path, conn, agg):
    """Même fixture exacte que test_median_of_a_group_without_castable_values_
    is_null_not_zero : median/percentile/stddev renvoient déjà null pour ce
    cas (design §3.1, `_agg_expr` — « Indéfini n'est PAS zéro... renvoyer 0
    produirait un graphique faux plutôt qu'un trou »), sum/avg/min/max
    doivent suivre la même règle plutôt que de renvoyer 0 silencieusement."""
    _write_partition(tmp_path, rows=[_row(1, "Nord", "pas-un-nombre", None, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg=agg, field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": None}]


def test_count_distinct_of_a_group_without_values_is_zero(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", None, 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="countDistinct", field="annee")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert rows == [{"region": "Nord", "value": 0}]


def test_percentile_without_p_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop")

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_percentile_out_of_range_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="percentile", field="pop", p=100)

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_p_on_a_non_percentile_agg_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", p=50)

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "p"


def test_measure_level_p_is_validated_independently(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region",
        measures=[AggregateMeasure(agg="percentile", field="pop", label="p90")],
    )

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )

    assert exc.value.field == "measures[0].p"


def test_two_percentile_measures_on_the_same_field_produce_two_columns(tmp_path, conn):
    """Le libellé dérivé d'une mesure `percentile` doit porter `p` : sans lui,
    deux centiles du même champ collisionnent et le pivot en perd un
    silencieusement (le dernier gagne)."""
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i * 10, lsn=1) for i in range(1, 11)],
    )
    request = AggregateRequestBody(
        groupBy="region",
        measures=[
            AggregateMeasure(agg="percentile", field="pop", p=50),
            AggregateMeasure(agg="percentile", field="pop", p=90),
        ],
    )

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert len(rows) == 1
    assert sorted(k for k in rows[0] if k != "region") == [
        "percentile50_pop",
        "percentile90_pop",
    ]
    assert rows[0]["percentile50_pop"] == pytest.approx(55.0, abs=1e-6)
    assert rows[0]["percentile90_pop"] == pytest.approx(91.0, abs=1e-6)


def test_bucket_groups_rows_by_year(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025-03-05", 10, lsn=1),
            _row(2, "Nord", "2025-11-20", 3, lsn=1),
            _row(3, "Nord", "2026-01-06", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="year", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2025-01-01 00:00:00", "value": 2},
        {"annee": "2026-01-01 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_quarter(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05", 10, lsn=1),
            _row(2, "Nord", "2026-02-20", 3, lsn=1),
            _row(3, "Nord", "2026-05-06", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="quarter", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-01 00:00:00", "value": 2},
        {"annee": "2026-04-01 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_hour(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2026-01-05 08:10:00", 10, lsn=1),
            _row(2, "Nord", "2026-01-05 08:55:00", 3, lsn=1),
            _row(3, "Nord", "2026-01-05 09:01:00", 4, lsn=1),
        ],
    )
    request = AggregateRequestBody(groupBy="annee", bucket="hour", agg="count")

    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 08:00:00", "value": 2},
        {"annee": "2026-01-05 09:00:00", "value": 1},
    ]


def test_sample_returns_bounded_values_for_the_field(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i, lsn=1) for i in range(1, 21)],
    )
    request = AggregateRequestBody(field="pop", sample=5)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert len(rows) == 5
    values = {r["value"] for r in rows}
    assert values.issubset(set(range(1, 21)))


def test_sample_returns_everything_when_more_requested_than_available(tmp_path, conn):
    rows = [_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)]
    # Sampling more rows than exist returns everything, not an error.
    # This indirectly exercises the WHERE value IS NOT NULL clause
    # (all rows pass the NOT NULL filter).
    _write_partition(tmp_path, rows=rows)
    request = AggregateRequestBody(field="pop", sample=100)

    _category_key, result_rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert {r["value"] for r in result_rows} == {10, 20}


def test_sample_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_bins_raises(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10, bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 2001):
        request = AggregateRequestBody(field="pop", sample=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="villes",
                table_info=TABLE_INFO,
                request=request,
            )
        assert exc.value.field == "sample"


def test_sample_on_empty_collection_returns_no_rows(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert rows == []
