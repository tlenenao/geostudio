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
    #
    # validate_condition_expr (AST-level, via app.analytics.sql_sandbox) is
    # only a first-pass rejection, NOT the security boundary — it can only
    # see the node types it knows to look for, and collect_table_refs only
    # recognizes BASE_TABLE nodes, not e.g. a DuckDB TABLE_FUNCTION node
    # (a table-valued function call in a FROM clause, such as
    # read_csv_auto(...)/read_parquet(...)/glob(...)). An expression like
    # "(SELECT count(*) FROM read_csv_auto('/etc/hostname')) > -1" passes
    # that scan untouched. The real boundary, matching
    # app.analytics.sql_sandbox.run_analyst_sql's own precedent (see that
    # module's docstring and its `_lock_down` before `_execute_bounded`),
    # is DuckDB's own connection lockdown — applied here too, before
    # executing anything. Inlined rather than importing the private
    # `_lock_down` helper, to keep this module's only dependency on
    # app.analytics.sql_sandbox its public API.
    #
    # Guarded by a current_setting() check rather than applied
    # unconditionally: once `lock_configuration=true` is set on a
    # connection, DuckDB refuses ANY further `SET` on that connection
    # (even re-setting the same value — confirmed empirically), so a
    # second evaluate_condition() call reusing an already-locked-down
    # connection would otherwise raise on the very statements meant to
    # keep it safe. This makes the lockdown idempotent: safe whether the
    # caller hands in a fresh connection per call (as today's tests do)
    # or a long-lived one reused across evaluations.
    #
    # If some other code already locked the connection's configuration
    # WITHOUT disabling external access, the setting can never be
    # changed again on that connection (that's the whole point of
    # lock_configuration) — there is no safe way to proceed, so this
    # raises rather than silently executing untrusted SQL on an open
    # connection.
    validate_condition_expr(conn, expr)
    locked, external_access = conn.execute(
        "SELECT current_setting('lock_configuration'), current_setting('enable_external_access')"
    ).fetchone()
    if locked and external_access:
        raise SqlSandboxError(
            "connection configuration is locked but external access was never disabled"
        )
    if not locked:
        conn.execute("SET enable_external_access = false")
        conn.execute("SET lock_configuration = true")
    row = conn.execute(f"SELECT ({expr}) FROM (SELECT ? AS value) t", [value]).fetchone()
    return bool(row[0])
