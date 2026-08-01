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
