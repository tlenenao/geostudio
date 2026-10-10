# SPDX-License-Identifier: Apache-2.0
"""Profil exploratoire d'une collection (REV-117 / GAP-23) — lac local tmp_path,
comme test_analytics_aggregate.py (DuckDB dispatche sur le schéma du chemin)."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics import profile as profile_mod
from app.analytics.profile import run_collection_profile
from app.collections.introspection import ColumnInfo, TableInfo

INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=False),
        ColumnInfo(name="creee", type="date", required=False),
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _write(base, rows):
    d = base / "tenant_id=t1" / "collection_id=villes" / "dt=2026-10-10"
    d.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(d / "p.parquet")


def _row(i, region, pop, creee="2020-01-01", op="insert", lsn=1, x=0.0, y=0.0):
    return {
        "id": i,
        "region": region,
        "pop": pop,
        "creee": creee,
        "_op": op,
        "_lsn": lsn,
        "_seq": 0,
        "_ts": 1.0,
        "geometry": Point(x, y),
    }


def _run(conn, tmp_path, masked=frozenset(), info=INFO):
    return run_collection_profile(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=info,
        masked_fields=masked,
    )


def _cols(result):
    return {c["name"]: c for c in result["columns"]}


def test_profile_per_column_stats(tmp_path, conn):
    _write(
        tmp_path,
        [
            _row(1, "Nord", 10, "2020-01-01", x=0, y=0),
            _row(2, "Sud", 20, "2021-06-01", x=2, y=4),
            _row(3, "Sud", None, None, x=1, y=1),
            _row(4, "Sud", 40, "2022-03-01", x=1, y=1),
            _row(5, "Sud", 30, "2022-03-02", op="delete", lsn=2),  # supprimée : exclue
            _row(5, "Sud", 30, "2022-03-02", lsn=1),
        ],
    )
    result = _run(conn, tmp_path)
    assert result["rowCount"] == 4
    assert result["sampled"] is False
    cols = _cols(result)
    assert "id" not in cols  # PK non profilée
    pop = cols["pop"]
    assert (pop["nonNull"], pop["nulls"], pop["distinct"]) == (3, 1, 3)
    assert (pop["min"], pop["max"]) == (10.0, 40.0)
    assert pop["median"] == 20.0
    assert pop["mean"] == pytest.approx(70 / 3)
    assert sum(b["count"] for b in pop["histogram"]) == 3
    region = cols["region"]
    assert region["topValues"][0] == {"value": "Sud", "count": 3}
    assert region["distinct"] == 2
    creee = cols["creee"]
    assert creee["nulls"] == 1
    assert creee["min"].startswith("2020-01-01") and creee["max"].startswith("2022-03-01")
    geom = result["geometry"]
    assert geom["bbox"] == [0.0, 0.0, 2.0, 4.0]
    assert geom["types"] == [{"type": "POINT", "count": 4}]


def test_profile_excludes_masked_fields(tmp_path, conn):
    _write(tmp_path, [_row(1, "Nord", 10)])
    result = _run(conn, tmp_path, masked=frozenset({"pop"}))
    assert "pop" not in _cols(result)
    assert "pop" not in str(result)


def test_profile_empty_lake_is_pending(tmp_path, conn):
    result = _run(conn, tmp_path)
    assert result["rowCount"] == 0
    assert result["columns"] == []
    assert result["geometry"] is None


def test_profile_caps_columns_and_samples(tmp_path, conn, monkeypatch):
    monkeypatch.setattr(profile_mod, "MAX_PROFILE_COLUMNS", 1)
    monkeypatch.setattr(profile_mod, "PROFILE_SAMPLE_ROWS", 2)
    _write(tmp_path, [_row(i, "A", i) for i in range(1, 6)])
    result = _run(conn, tmp_path)
    assert result["truncatedColumns"] is True
    assert len(result["columns"]) == 1
    assert result["sampled"] is True
    assert result["rowCount"] == 5
    assert result["columns"][0]["nonNull"] == 2  # statistiques sur l'échantillon


def test_profile_ignores_column_missing_from_lake(tmp_path, conn):
    _write(tmp_path, [_row(1, "Nord", 10)])
    info = TableInfo(
        **{
            **INFO.__dict__,
            "columns": [*INFO.columns, ColumnInfo(name="absente", type="string", required=False)],
        }
    )
    assert "absente" not in _cols(_run(conn, tmp_path, info=info))
