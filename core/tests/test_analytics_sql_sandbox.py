# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import (
    SqlSandboxError, collect_table_refs, parse_ast, validate_select_only,
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_select_only_accepts_select(conn):
    validate_select_only(parse_ast(conn, "SELECT 1"))  # ne lève pas


def test_select_only_rejects_non_select(conn):
    for sql in ["CREATE TABLE x(i int)", "COPY (SELECT 1) TO 'x'", "ATTACH 'y.db'", "PRAGMA version"]:
        with pytest.raises(SqlSandboxError):
            validate_select_only(parse_ast(conn, sql))


def test_select_only_rejects_multiple_statements(conn):
    with pytest.raises(SqlSandboxError):
        validate_select_only(parse_ast(conn, "SELECT 1; SELECT 2"))


def test_parse_ast_rejects_syntax_error(conn):
    with pytest.raises(SqlSandboxError):
        parse_ast(conn, "SELECT FROM WHERE")


def test_collect_table_refs_finds_base_tables(conn):
    refs = collect_table_refs(parse_ast(conn, "SELECT * FROM villes v JOIN routes r ON r.id = v.id"))
    assert {"villes", "routes"} <= refs
