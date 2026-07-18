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

import duckdb

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
