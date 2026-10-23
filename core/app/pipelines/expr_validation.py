# SPDX-License-Identifier: Apache-2.0
"""Validation d'une expression scalaire SQL DuckDB bornée pour
transform.filter/transform.derive/transform.aggregate.metrics (design SP-15a
§5.1 — correction de l'étude de faisabilité, qui affirmait à tort qu'un
moteur CEL tournait déjà côté serveur). Réutilise le même mécanisme AST que
app.analytics.sql_sandbox (json_serialize_sql), restreint à UNE expression
scalaire enveloppée dans un SELECT sans FROM — jamais un SELECT complet,
jamais une référence de table."""

import duckdb

from app.analytics.sql_sandbox import (
    SqlSandboxError,
    _function_names,
    collect_table_refs,
    parse_ast,
    validate_select_only,
)

_FILE_FUNCTION_PREFIXES = (
    "read_",
    "st_read",
    "glob",
    "parquet_",
    "sniff_csv",
    "iceberg_",
    "delta_scan",
    "query",
)


def validate_bounded_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None:
    ast = parse_ast(conn, f"SELECT ({expr})")
    validate_select_only(ast)
    if collect_table_refs(ast):
        raise SqlSandboxError("expression must not reference a table")
    # AUD-159 : une expression scalaire ne lit jamais un fichier (read_text, glob, st_read…).
    bad = sorted({n for n in _function_names(ast) if n.startswith(_FILE_FUNCTION_PREFIXES)})
    if bad:
        raise SqlSandboxError(f"function not allowed in an expression: {', '.join(bad)}")
