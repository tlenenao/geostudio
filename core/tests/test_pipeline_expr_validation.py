# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.expr_validation import validate_bounded_expr


@pytest.fixture()
def conn():
    return duckdb.connect(":memory:")


def test_valid_scalar_expression_passes(conn):
    validate_bounded_expr(conn, "1 + 1")


def test_valid_boolean_expression_passes(conn):
    validate_bounded_expr(conn, "pop > 1000")


def test_invalid_syntax_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "pop >")


def test_expression_referencing_a_table_raises(conn):
    with pytest.raises(SqlSandboxError, match="must not reference a table"):
        validate_bounded_expr(conn, "(SELECT 1 FROM some_table)")


def test_injection_attempt_via_closing_paren_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "1) UNION SELECT password FROM users--")
