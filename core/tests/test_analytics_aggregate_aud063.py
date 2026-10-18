# SPDX-License-Identifier: Apache-2.0
"""AUD-063 : top-N, opérateurs de filtre, cache de résultat de l'agrégat (DuckDB sur
chemins locaux, comme test_analytics_aggregate)."""

import geopandas as gpd
import pytest

from app.analytics import aggregate as agg_mod
from app.analytics.aggregate import (
    AggregateMeasure,
    AggregateRequestBody,
    UnknownAggregateField,
    run_collection_aggregate,
)
from tests.test_analytics_aggregate import TABLE_INFO, _row, _write_partition, conn  # noqa: F401


def _run(duck, tmp_path, request, masked=frozenset()):
    return run_collection_aggregate(
        duck,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
        masked_fields=masked,
    )


def _three_regions(tmp_path):
    _write_partition(
        tmp_path,
        rows=[
            _row(1, "Nord", "2025", 10),
            _row(2, "Nord", "2026", 30),
            _row(3, "Sud", "2025", 5),
            _row(4, "Est", "2025", 20),
            _row(5, "Ouest_1", "2025", 1),
        ],
    )


def test_top_n_orders_by_measure_and_limits(tmp_path, conn):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(
        groupBy="region", agg="sum", field="pop", orderBy="value", order="desc", limit=2
    )
    _, rows = _run(conn, tmp_path, request)
    assert [r["region"] for r in rows] == ["Nord", "Est"]
    _, asc = _run(conn, tmp_path, request.model_copy(update={"order": "asc", "limit": 1}))
    assert [r["region"] for r in asc] == ["Ouest_1"]


def test_top_n_by_named_measure_multi_group(tmp_path, conn):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(
        groupBy=["region", "annee"],
        measures=[AggregateMeasure(field="pop", agg="max", label="biggest")],
        orderBy="biggest",
        limit=1,
    )
    _, rows = _run(conn, tmp_path, request)
    assert rows == [{"region": "Nord", "annee": "2026", "biggest": 30.0}]


@pytest.mark.parametrize(
    "extra",
    [
        {"limit": 3},  # limit sans orderBy
        {"orderBy": "region", "split": "annee"},  # split
        {"orderBy": "nope"},  # libellé inconnu
        {"orderBy": "region", "limit": 0},
    ],
)
def test_top_n_rejects_invalid_combinations(tmp_path, conn, extra):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", **extra)
    with pytest.raises(UnknownAggregateField):
        _run(conn, tmp_path, request)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"region__ne": "Nord"}, {"Sud", "Est", "Ouest_1"}),
        ({"pop__gt": "10"}, {"Nord", "Est"}),
        ({"pop__lt": "10"}, {"Sud", "Ouest_1"}),
        ({"region__contains": "ES"}, {"Ouest_1", "Est"}),
        ({"region__contains": "_"}, {"Ouest_1"}),  # joker LIKE neutralisé
    ],
)
def test_filter_operators(tmp_path, conn, filters, expected):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(groupBy="region", agg="count", filters=filters)
    _, rows = _run(conn, tmp_path, request)
    assert {r["region"] for r in rows} == expected


def test_result_cache_hits_and_invalidates_on_new_file(tmp_path, conn):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")
    before = len(agg_mod._result_cache)
    _, first = _run(conn, tmp_path, request)
    assert len(agg_mod._result_cache) == before + 1
    first.append({"region": "mutation"})  # le cache rend des copies
    _, second = _run(conn, tmp_path, request)
    assert {"region": "mutation"} not in second
    # Une nouvelle écriture CDC (nouveau fichier) invalide : la clé change.
    part = tmp_path / "tenant_id=t1" / "collection_id=villes" / "dt=2026-07-18"
    frame = gpd.GeoDataFrame(
        [_row(6, "Centre", "2026", 99, lsn=2)], geometry="geometry", crs="EPSG:4326"
    )
    frame.to_parquet(part / "part-2.parquet")
    _, third = _run(conn, tmp_path, request)
    assert "Centre" in {r["region"] for r in third}


def test_result_cache_is_partitioned_by_masked_fields(tmp_path, conn):  # noqa: F811
    _three_regions(tmp_path)
    request = AggregateRequestBody(groupBy="region", agg="count")
    _run(conn, tmp_path, request)
    with pytest.raises(UnknownAggregateField):  # un lecteur masqué ne lit pas l'entrée de l'autre
        _run(conn, tmp_path, request, masked=frozenset({"region"}))
