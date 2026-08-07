# SPDX-License-Identifier: Apache-2.0
"""Bounded scalar SQL condition expression for kind="alert" (design SP-16b
§4). Lives in app.configs, not app.alerts, deliberately: app.alerts sits
ABOVE app.secrets in the import-linter layer contract (Global Constraints),
so if this lived in app.alerts, app.configs (a lower layer, needed for the
save-time Pydantic validator in schemas.py) could not import it back. The
function has no alert-specific knowledge — it is a generic "one bounded
scalar SQL expression, no table references" helper, same restriction as
app.pipelines.expr_validation.validate_bounded_expr but placed where both
the save-time validator (app.configs) and the run-time evaluator
(app.alerts, Task 9) can import it downward without crossing the contract.
"""
import duckdb

from app.analytics.sql_sandbox import collect_table_refs, parse_ast, validate_select_only, SqlSandboxError


def validate_condition_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None:
    ast = parse_ast(conn, f"SELECT ({expr})")
    validate_select_only(ast)
    if collect_table_refs(ast):
        raise SqlSandboxError("condition expression must not reference a table")


def evaluate_condition(conn: duckdb.DuckDBPyConnection, expr: str, value: float) -> bool:
    # `value` is bound as a real column of a derived table rather than
    # string-substituted into expr — avoids any risk of a naive text
    # replace corrupting the expression (e.g. "value" appearing inside a
    # string literal), and lets DuckDB's own SQL scoping resolve the bare
    # identifier normally.
    validate_condition_expr(conn, expr)
    row = conn.execute(f"SELECT ({expr}) FROM (SELECT ? AS value) t", [value]).fetchone()
    return bool(row[0])
