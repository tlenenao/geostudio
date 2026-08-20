# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.configs.alert_condition import evaluate_condition, validate_condition_expr


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_validate_condition_expr_accepts_a_bounded_comparison(conn):
    validate_condition_expr(conn, "value > 100")  # must not raise


def test_validate_condition_expr_rejects_a_table_reference(conn):
    with pytest.raises(SqlSandboxError):
        validate_condition_expr(conn, "(SELECT count(*) FROM some_table)")


def test_validate_condition_expr_rejects_invalid_sql(conn):
    with pytest.raises(SqlSandboxError):
        validate_condition_expr(conn, "value >")


def test_evaluate_condition_returns_true_when_condition_holds(conn):
    assert evaluate_condition(conn, "value > 100", 150.0) is True


def test_evaluate_condition_returns_false_when_condition_does_not_hold(conn):
    assert evaluate_condition(conn, "value > 100", 50.0) is False


def test_evaluate_condition_supports_compound_expressions(conn):
    assert evaluate_condition(conn, "value >= 10 AND value <= 20", 15.0) is True
    assert evaluate_condition(conn, "value >= 10 AND value <= 20", 25.0) is False


def test_evaluate_condition_rejects_table_function_file_read_bypass(conn):
    # collect_table_refs only recognizes BASE_TABLE AST nodes, not
    # TABLE_FUNCTION nodes — a table-valued function call in a FROM clause
    # (read_csv_auto/read_parquet/glob/...) slips past that AST scan
    # entirely. Without a real DuckDB connection lockdown, this expression
    # performs a genuine local file read. It must be rejected — by the AST
    # scan improving, or (as implemented) by DuckDB's own connection
    # lockdown refusing the file access — not silently executed.
    expr = "(SELECT count(*) FROM read_csv_auto('/etc/hostname')) > -1"
    # Deliberately bounded to the two mechanisms the docstring above says
    # are allowed to catch this (AST scan -> SqlSandboxError, or DuckDB's
    # own connection lockdown -> duckdb.Error e.g. PermissionException,
    # confirmed empirically), not a bare Exception — so this assertion
    # can't be satisfied by an unrelated bug (e.g. a TypeError from a typo
    # elsewhere in evaluate_condition).
    with pytest.raises((SqlSandboxError, duckdb.Error)):
        evaluate_condition(conn, expr, 0.0)


def test_evaluate_condition_locks_down_connection_before_executing(conn):
    evaluate_condition(conn, "value > 100", 150.0)
    locked, external_access = conn.execute(
        "SELECT current_setting('lock_configuration'), current_setting('enable_external_access')"
    ).fetchone()
    assert locked is True
    assert external_access is False


def test_evaluate_condition_is_safe_to_call_twice_on_the_same_connection(conn):
    # lock_configuration=true is permanent for a connection — a naive
    # unconditional SET on every call would raise on the second call once
    # the first call has already locked it down.
    assert evaluate_condition(conn, "value > 100", 150.0) is True
    assert evaluate_condition(conn, "value > 100", 50.0) is False


def test_evaluate_condition_bounds_a_compute_bound_table_function(conn, monkeypatch):
    # Second sandbox bypass, distinct from the file-read/SSRF one covered by
    # test_evaluate_condition_rejects_table_function_file_read_bypass above:
    # a table function that performs NO external I/O at all (e.g. DuckDB's
    # builtin range()) is unaffected by enable_external_access=false and
    # still slips past collect_table_refs (BASE_TABLE-only, not
    # TABLE_FUNCTION). Without a statement timeout, this cross join is
    # effectively unbounded compute and would hang the worker evaluating
    # alerts. STATEMENT_TIMEOUT_S is monkeypatched down so the test itself
    # stays fast and deterministic rather than needing a genuinely
    # long-running query.
    monkeypatch.setattr("app.configs.alert_condition.STATEMENT_TIMEOUT_S", 0.2)
    expr = "(SELECT count(*) FROM range(100000000000) t1, range(100000) t2) > -1"
    validate_condition_expr(conn, expr)  # must NOT raise -- confirms the bypass is real
    with pytest.raises(SqlSandboxError):
        evaluate_condition(conn, expr, 0.0)
