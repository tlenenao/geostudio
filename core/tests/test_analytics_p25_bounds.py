# SPDX-License-Identifier: Apache-2.0
"""P25 : bornes (mémoire, threads, temps, groupes) et exactitude des agrégats.
Chaque borne a un test qui échoue sans elle (falsifié à la main)."""

import duckdb
import pytest

from app.analytics import aggregate
from app.analytics.aggregate import (
    AggregateRequestBody,
    UnknownAggregateField,
    aggregate_columns,
    lake_as_of,
    run_collection_aggregate,
)
from app.analytics.duckdb_conn import open_connection
from app.analytics.export import rows_to_csv, rows_to_xlsx
from app.analytics.sql_sandbox import _coerce
from app.collections.introspection import ColumnInfo, TableInfo

INFO = TableInfo(
    table_name="t",
    pk_column="id",
    geometry_column=None,
    geometry_type=None,
    srid=None,
    columns=[
        ColumnInfo(name="cat", type="string", required=False),
        ColumnInfo(name="montant", type="integer", required=False),
        ColumnInfo(name="d", type="datetime", required=False),
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _lake(tmp_path, select_sql):
    part = tmp_path / "tenant_id=t1" / "collection_id=c1" / "dt=2026-01-01"
    part.mkdir(parents=True)
    duckdb.connect().execute(f"COPY ({select_sql}) TO '{part}/p.parquet' (FORMAT parquet)")


SMALL = """SELECT * FROM (VALUES
  (1,'b',10,'2025-02-10T10:00:00+00:00','insert',1,0,5.0),
  (2,NULL,20,'2025-01-15T10:00:00+00:00','insert',1,1,5.0),
  (3,'a',30,'2025-03-01T00:00:00+00:00','insert',1,2,5.0))
  t(id,cat,montant,d,_op,_lsn,_seq,_ts)"""


def _agg(conn, tmp_path, **kw):
    return run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="c1",
        table_info=INFO,
        request=AggregateRequestBody(**kw),
    )


def test_open_connection_bounds_memory_and_threads(monkeypatch):
    monkeypatch.setenv("CORE_DUCKDB_MEMORY_LIMIT", "300MB")
    monkeypatch.setenv("CORE_DUCKDB_THREADS", "3")
    c = open_connection(endpoint_url="http://m:9000", access_key="a", secret_key="s")
    assert "286" in c.execute("select current_setting('memory_limit')").fetchone()[0]
    assert c.execute("select current_setting('threads')").fetchone()[0] == 3


def test_pathological_aggregate_is_interrupted(tmp_path, conn, monkeypatch):
    _lake(
        tmp_path,
        "SELECT i AS id, CAST(i AS VARCHAR) AS cat, i AS montant, '2025-01-01' AS d, "
        "'insert' AS _op, 1 AS _lsn, 0 AS _seq, 5.0 AS _ts FROM range(4000000) r(i)",
    )
    monkeypatch.setenv("CORE_DUCKDB_STATEMENT_TIMEOUT_S", "0.05")
    with pytest.raises(UnknownAggregateField, match="time limit"):
        _agg(conn, tmp_path, agg="median", field="montant")


def test_group_count_is_capped(tmp_path, conn, monkeypatch):
    _lake(tmp_path, SMALL)
    monkeypatch.setattr(aggregate, "MAX_GROUPS", 2)
    with pytest.raises(UnknownAggregateField, match="too many groups"):
        _agg(conn, tmp_path, groupBy="montant")


def test_buckets_sorted_and_null_group_is_null(tmp_path, conn):
    _lake(tmp_path, SMALL)
    _, rows = _agg(conn, tmp_path, groupBy="d", bucket="month")
    keys = [r["d"] for r in rows]
    assert keys == sorted(keys) and len(keys) == 3
    _, rows = _agg(conn, tmp_path, groupBy="cat")
    assert [r["cat"] for r in rows] == ["a", "b", None]


def test_count_on_empty_filter_is_zero(tmp_path, conn):
    _lake(tmp_path, SMALL)
    _, rows = _agg(conn, tmp_path, agg="count", filters={"cat": "zz"})
    assert rows[0]["value"] == 0


def test_invalid_filter_value_is_a_business_error(tmp_path, conn):
    _lake(tmp_path, SMALL)
    with pytest.raises(UnknownAggregateField, match="invalid filter"):
        _agg(conn, tmp_path, agg="count", filters={"montant__gte": "abc"})


def test_single_day_range_on_datetime_keeps_that_day(tmp_path, conn):
    _lake(tmp_path, SMALL)
    _, rows = _agg(
        conn, tmp_path, agg="count", filters={"d__gte": "2025-01-15", "d__lte": "2025-01-15"}
    )
    assert rows[0]["value"] == 1


def test_infinite_values_are_rendered_null():
    assert _coerce(float("inf")) is None and _coerce(float("nan")) is None


def test_sql_lab_infinite_result_is_json_safe(conn):
    import json

    from app.analytics.sql_sandbox import run_analyst_sql

    _cols, rows, _t = run_analyst_sql(
        conn, sql="select 'inf'::double as x", allowed={}, base_uri="", tenant_id="t1"
    )
    json.dumps(rows, allow_nan=False)
    assert rows == [[None]]


def test_empty_export_keeps_the_header_row():
    req = AggregateRequestBody(groupBy="cat", agg="count")
    cols = aggregate_columns(req, "cat")
    assert cols == ["cat", "value"]
    assert rows_to_csv([], cols).decode().strip() == "cat,value"
    assert rows_to_xlsx([], cols)


def test_lake_as_of_reports_latest_flush_or_none(tmp_path, conn):
    assert lake_as_of(conn, str(tmp_path), "t1", "c1") is None
    _lake(tmp_path, SMALL)
    assert lake_as_of(conn, str(tmp_path), "t1", "c1") == "1970-01-01T00:00:05+00:00"


def test_shell_contains_filter_form_is_case_insensitive_with_literal_wildcards():
    """P25.13 : forme SQL produite par compileFilter.ts, vérifiée sur DuckDB."""
    c = duckdb.connect()
    q = "select ? ILIKE ? ESCAPE '\\'"
    assert c.execute(q, ["N1_x", "%n1\\_%"]).fetchone()[0] is True
    assert c.execute(q, ["abc", "%\\_%"]).fetchone()[0] is False
