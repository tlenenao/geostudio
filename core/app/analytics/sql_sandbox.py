# SPDX-License-Identifier: Apache-2.0
"""Moteur d'isolation du SQL analyste (SP-11c). La frontière de sécurité est
DuckDB (SET enable_external_access=false + lock_configuration=true, cf.
run_analyst_sql), PAS ces fonctions d'AST : parse_ast/validate_select_only/
collect_table_refs servent seulement à rejeter tôt le non-SELECT et à décider
quelles vues matérialiser. Chaînes de nœuds AST confirmées par le spike
scripts/spike_duckdb_sql_sandbox.py (Task 1) — y compris SET_OPERATION_NODE,
re-confirmé directement en Task 7 via `SELECT 1 UNION SELECT 2`.

Correction empirique reportée du spike (Task 1) : `duckdb.Exception` n'existe
pas en DuckDB 1.5.4 (AttributeError à l'exécution) — la base commune réelle
de toutes les exceptions DuckDB est `duckdb.Error`, utilisée ci-dessous."""
import json
import threading
from datetime import date, datetime
from decimal import Decimal

import duckdb

from app.analytics.aggregate import _dedup_cte, _has_any_file, _qi

ROW_CAP = 10_000
STATEMENT_TIMEOUT_S = 10.0
MEMORY_LIMIT = "512MB"
THREADS = 2

# Types de nœuds json_serialize_sql (confirmés par le spike Task 1 + re-confirmés
# en Task 7 pour SET_OPERATION_NODE via `SELECT 1 UNION SELECT 2`) :
_SELECT_NODE_TYPES = {"SELECT_NODE", "SET_OPERATION_NODE"}
_BASE_TABLE_TYPE = "BASE_TABLE"


class SqlSandboxError(Exception):
    """Erreur SQL analyste destinée à un 400."""


def parse_ast(conn: duckdb.DuckDBPyConnection, sql: str) -> dict:
    try:
        raw = conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
    except duckdb.Error as exc:
        raise SqlSandboxError(f"invalid SQL: {exc}") from exc
    doc = json.loads(raw)
    if doc.get("error"):
        raise SqlSandboxError(doc.get("error_message") or "invalid SQL")
    return doc


def validate_select_only(ast: dict) -> None:
    statements = ast.get("statements", [])
    if len(statements) != 1:
        raise SqlSandboxError("exactly one SELECT statement is required")
    node = statements[0].get("node", {})
    if node.get("type") not in _SELECT_NODE_TYPES:
        raise SqlSandboxError("only read-only SELECT queries are allowed")


def collect_table_refs(ast: dict) -> set[str]:
    found: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("type") == _BASE_TABLE_TYPE and isinstance(obj.get("table_name"), str):
                found.add(obj["table_name"])
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(ast)
    return found


def _apply_limits(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    conn.execute(f"SET threads = {THREADS}")


def _materialize(conn, *, name, table_info, base_uri, tenant_id) -> None:
    if not _has_any_file(conn, base_uri, tenant_id, name):
        raise SqlSandboxError(f"collection '{name}' has no data yet")
    cte = _dedup_cte(table_info, base_uri, tenant_id, name)
    conn.execute(f"CREATE TEMP TABLE {_qi(name)} AS {cte} SELECT * FROM live")


def _lock_down(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")


def _coerce(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _execute_bounded(conn, sql):
    timer = threading.Timer(STATEMENT_TIMEOUT_S, conn.interrupt)
    timer.start()
    try:
        cur = conn.execute(sql)
        fetched = cur.fetchmany(ROW_CAP + 1)
        columns = [d[0] for d in cur.description]
    except duckdb.InterruptException as exc:
        raise SqlSandboxError("query exceeded the time limit") from exc
    except duckdb.Error as exc:
        raise SqlSandboxError(str(exc)) from exc
    finally:
        timer.cancel()
    truncated = len(fetched) > ROW_CAP
    rows = [[_coerce(v) for v in row] for row in fetched[:ROW_CAP]]
    return columns, rows, truncated


def run_analyst_sql(conn, *, sql, allowed, base_uri, tenant_id):
    """Exécute le SQL de l'analyste confiné aux vues autorisées. `allowed` :
    {collection_id: TableInfo}. Retourne (columns, rows, truncated). L'ordre est
    critique : matérialiser (accès externe encore ouvert) PUIS verrouiller PUIS
    exécuter — jamais l'inverse."""
    ast = parse_ast(conn, sql)
    validate_select_only(ast)
    refs = collect_table_refs(ast)
    _apply_limits(conn)
    for name in sorted(refs & set(allowed)):
        _materialize(conn, name=name, table_info=allowed[name], base_uri=base_uri, tenant_id=tenant_id)
    _lock_down(conn)
    return _execute_bounded(conn, sql)
