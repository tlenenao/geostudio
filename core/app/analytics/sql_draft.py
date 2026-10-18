# SPDX-License-Identifier: Apache-2.0
"""Validation d'un brouillon SQL généré par un LLM (AUD-104, D23-04).

Avant de renvoyer un `generate_sql_query` à l'utilisateur : un SELECT unique, des
tables limitées à la collection demandée (hors CTE locales) et un dry-run de liaison
(`EXPLAIN`) sur une table vide de même schéma — colonne ou table inconnue = erreur
renvoyée au LLM pour réparation. Ne remplace pas la sandbox d'exécution
(`run_analyst_sql`), qui reste la frontière de sécurité."""

from typing import Any

import duckdb

from app.analytics.sql_sandbox import (
    SqlSandboxError,
    collect_table_refs,
    parse_ast,
    validate_select_only,
)
from app.sql_ident import quote_ident_duckdb as _qi

_DUCKDB_TYPES = {
    "integer": "BIGINT",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "datetime": "TIMESTAMPTZ",
    "date": "DATE",
}


def _cte_names(node: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        cte_map = node.get("cte_map")
        if isinstance(cte_map, dict):
            for entry in cte_map.get("map") or []:
                if isinstance(entry, dict) and isinstance(entry.get("key"), str):
                    names.add(entry["key"])
        for value in node.values():
            names |= _cte_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= _cte_names(value)
    return names


def validate_draft_sql(
    sql: str,
    *,
    table: str,
    fields: list[dict[str, Any]],
    extra_columns: tuple[str, ...] = (),
) -> None:
    """Lève SqlSandboxError (message destiné au LLM puis à l'utilisateur).
    `extra_columns` : pk et colonne géométrie, absentes de la liste de champs."""
    conn = duckdb.connect(":memory:")
    try:
        ast = parse_ast(conn, sql)
        validate_select_only(ast)
        foreign = collect_table_refs(ast) - _cte_names(ast) - {table}
        if foreign:
            raise SqlSandboxError(
                f"table non autorisée : {', '.join(sorted(foreign))} (seule {table!r} est permise)"
            )
        spatial = True
        try:
            conn.execute("LOAD spatial")
        except duckdb.Error:
            spatial = False
        if not spatial and "st_" in sql.lower():
            return  # fonctions spatiales non vérifiables ici : la sandbox tranchera
        defs = [
            f"{_qi(f['name'])} {_DUCKDB_TYPES.get(f.get('type', ''), 'VARCHAR')}" for f in fields
        ]
        geom_type = "GEOMETRY" if spatial else "BLOB"
        defs += [f"{_qi(c)} {geom_type}" for c in extra_columns]
        conn.execute(f"CREATE TEMP TABLE {_qi(table)} ({', '.join(defs)})")
        conn.execute("SET enable_external_access = false")
        try:
            conn.execute(f"EXPLAIN {sql}")
        except duckdb.BinderException as exc:
            raise SqlSandboxError(str(exc).splitlines()[0]) from exc
        except duckdb.CatalogException as exc:
            if "Table with name" in str(exc):
                raise SqlSandboxError(str(exc).splitlines()[0]) from exc
        except duckdb.Error:
            # Autre erreur de liaison (typage…) : pas assez fiable pour rejeter,
            # la sandbox tranchera à l'exécution.
            pass
    finally:
        conn.close()
