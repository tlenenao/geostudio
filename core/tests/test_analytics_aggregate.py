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
    AggregateMeasure, AggregateRequestBody, UnknownAggregateField, run_collection_aggregate,
)
from app.collections.introspection import ColumnInfo, TableInfo

TABLE_INFO = TableInfo(
    table_name="villes", pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
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
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _row(id_, region, annee, pop, *, op="insert", lsn=1, x=0.0, y=0.0):
    return {"id": id_, "region": region, "annee": annee, "pop": pop, "_op": op, "_lsn": lsn,
            "_ts": 1.0, "geometry": Point(x, y)}


def test_group_by_with_split_produces_wide_rows_matching_client_contract(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 12, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1), _row(4, "Sud", "2026", 7, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", split="annee", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "region"
    by_region = {r["region"]: r for r in rows}
    assert by_region["Nord"] == {"region": "Nord", "2025": 10, "2026": 12}
    assert by_region["Sud"] == {"region": "Sud", "2025": 5, "2026": 7}


def test_group_by_without_split_uses_single_measure_labeled_value(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "region"
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10}, {"region": "Sud", "value": 5},
    ]


def test_multiple_measures_use_their_own_labels(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region",
        measures=[AggregateMeasure(agg="sum", field="pop", label="total"),
                  AggregateMeasure(agg="count", label="nb")],
    )

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "total": 30, "nb": 2}]


def test_no_group_by_produces_a_single_total_row(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "group"
    assert rows == [{"group": "Total", "value": 15}]


def test_reduces_to_current_state_last_lsn_wins_and_tombstone_excluded(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1),
        _row(1, "Nord", "2025", 999, lsn=5),  # update : doit gagner
        _row(2, "Sud", "2025", 5, lsn=1),
        _row(2, "Sud", "2025", 0, lsn=2, op="delete"),  # tombstone : doit disparaître
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 999}]  # Sud entièrement supprimé


def test_attribute_filter_narrows_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", filters={"region": "Nord"})

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_bbox_filter_narrows_rows_spatially(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1, x=2.3, y=48.8),  # dans le bbox
        _row(2, "Sud", "2025", 5, lsn=1, x=100.0, y=50.0),  # hors bbox
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", bbox=(2.0, 48.0, 3.0, 49.0))

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_empty_collection_returns_empty_rows_without_error(tmp_path, conn):
    # Aucune partition écrite du tout — même chemin que "collection jamais flushée".
    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=AggregateRequestBody(groupBy="region"),
    )
    assert category_key == "region"
    assert rows == []


def test_unknown_group_by_field_raises_with_field_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="inconnu")
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc_info.value.field == "groupBy"


def test_bbox_without_geometry_column_raises():
    info_no_geom = TableInfo(table_name="t", pk_column="id", geometry_column=None,
                             geometry_type=None, srid=None, columns=[])
    request = AggregateRequestBody(bbox=(0, 0, 1, 1))
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            duckdb.connect(":memory:"), base_uri="/nonexistent", tenant_id="t1",
            collection_id="c", table_info=info_no_geom, request=request,
        )
    assert exc_info.value.field == "bbox"


def test_gte_lte_filters_narrow_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 20, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop",
                                    filters={"annee__gte": "2026"})
    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )
    assert rows == [{"region": "Nord", "value": 20}]


def test_in_filter_matches_any_listed_value(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1),
        _row(3, "Est", "2025", 3, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop",
                                    filters={"region__in": "Nord,Sud"})
    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10}, {"region": "Sud", "value": 5},
    ]


def test_suffixed_filter_on_unknown_field_raises_with_stripped_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", filters={"inconnu__gte": "1"})
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert "inconnu" in str(exc_info.value)


def test_bucket_groups_rows_by_day(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
        _row(3, "Nord", "2026-01-06", 4, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="count")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "annee"
    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 00:00:00", "value": 2},
        {"annee": "2026-01-06 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_month(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Nord", "2026-01-20", 5, lsn=1),
        _row(3, "Nord", "2026-02-10", 7, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="month", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
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
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bucket"


def test_bucket_on_non_castable_field_groups_under_a_null_bucket(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "pas-une-date", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    by_key = {r["annee"]: r["value"] for r in rows}
    assert by_key["None"] == 10
    assert by_key["2026-01-05 00:00:00"] == 3


def test_groupby_list_with_duplicate_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "region"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "groupBy"


def test_bucket_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], bucket="day")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bucket"


def test_split_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], split="annee")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "split"


def test_groupby_list_with_unknown_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "inconnu"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "groupBy"


def test_two_field_groupby_produces_tidy_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 12, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy=["region", "annee"], agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
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
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1),
    ])
    request = AggregateRequestBody(groupBy=["region", "annee", "pop"], agg="count")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == ["region", "annee", "pop"]
    assert sorted(rows, key=lambda r: r["pop"]) == [
        {"region": "Nord", "annee": "2025", "pop": 10, "value": 1},
        {"region": "Nord", "annee": "2025", "pop": 20, "value": 1},
    ]


def test_multi_field_groupby_with_multiple_measures(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(
        groupBy=["region", "annee"],
        measures=[AggregateMeasure(agg="sum", field="pop", label="total"),
                  AggregateMeasure(agg="count", label="nb")],
    )

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "annee": "2025", "total": 30, "nb": 2},
        {"region": "Sud", "annee": "2025", "total": 5, "nb": 1},
    ]


def test_bins_produces_equal_width_buckets(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 1, lsn=1), _row(2, "Nord", "2025", 2, lsn=1),
        _row(3, "Nord", "2025", 9, lsn=1), _row(4, "Nord", "2025", 10, lsn=1),
    ])
    request = AggregateRequestBody(field="pop", bins=3)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    # pop in [1, 10], 3 bins of width 3 → [1,4), [4,7), [7,10] (last bin absorbs the max via LEAST clamp)
    by_index = {r["bucketIndex"]: r["count"] for r in rows}
    assert by_index == {0: 2, 2: 2}  # pop 1,2 → bin 0 ; pop 9,10 → bin 2 (clamped) ; bin 1 empty, absent


def test_bins_on_a_constant_field_returns_one_bucket(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 5, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(field="pop", bins=4)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 5.0, "bucketEnd": 5.0, "count": 2}]


def test_bins_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bins"


def test_bins_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bins"


def test_bins_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 101):
        request = AggregateRequestBody(field="pop", bins=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
                table_info=TABLE_INFO, request=request,
            )
        assert exc.value.field == "bins"


def test_bins_narrowed_by_attribute_filter(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 1, lsn=1), _row(2, "Sud", "2025", 9, lsn=1),
    ])
    request = AggregateRequestBody(field="pop", bins=2, filters={"region": "Nord"})

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 1.0, "bucketEnd": 1.0, "count": 1}]


def test_bins_excludes_non_numeric_values_from_top_bucket(tmp_path, conn):
    """Regression test: non-numeric strings should be filtered out by TRY_CAST,
    not silently miscounted into the top bucket by DuckDB's NULL-ignoring LEAST."""
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", "1", lsn=1),     # numeric string
        _row(2, "Nord", "2025", "2", lsn=1),     # numeric string
        _row(3, "Nord", "2025", "abc", lsn=1),   # non-numeric string → TRY_CAST → NULL
        _row(4, "Nord", "2025", "10", lsn=1),    # numeric string (max)
    ])
    request = AggregateRequestBody(field="pop", bins=3)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    # After TRY_CAST("1"/"2"/"abc"/"10" AS DOUBLE): 1.0, 2.0, NULL, 10.0
    # lo=1.0, hi=10.0, width=3.0
    # Bucket 0: [1, 4) contains 1.0, 2.0 → count=2
    # Bucket 2: [7, 10] contains 10.0 → count=1
    # "abc" should NOT appear in any bucket; total count must be 3, not 4
    by_index = {r["bucketIndex"]: r["count"] for r in rows}
    assert by_index == {0: 2, 2: 1}, f"Expected {{0: 2, 2: 1}}, got {by_index}"
    total_count = sum(r["count"] for r in rows)
    assert total_count == 3, f"Expected total count 3, got {total_count} (non-numeric 'abc' was not excluded)"
