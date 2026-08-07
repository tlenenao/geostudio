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
