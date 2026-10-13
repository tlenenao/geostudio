# SPDX-License-Identifier: Apache-2.0
"""Famille Database (ARC vague 4, voie M, F8) : `transform.sqlExecutor`.

SQL **en lecture seule** sur les données du flux (qui vient du lac via reader.collection, donc
déjà sous RLS/masquage/limites géographiques) : un unique SELECT, qui ne voit que l'entrée sous
le nom `input`. Réutilise les primitives AST de la sandbox SQL-analyste ; la vraie frontière de
sécurité reste la connexion DuckDB verrouillée du runtime (`enable_external_access=false`), ces
contrôles rejettent tôt DROP/ATTACH/COPY/INSERT, les tables étrangères et les fonctions-tables."""

from typing import Any

from pydantic import BaseModel, Field

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only
from app.sql_ident import quote_ident_duckdb as _qi

_INPUT = "input"


class TransformSqlExecutorParams(BaseModel):
    """Exécute une requête SQL SELECT (lecture seule) sur l'entrée, nommée `input` dans la
    requête. Le résultat devient le flux de sortie : garder la colonne `geometry` pour la suite
    d'un pipeline spatial. Toute instruction qui n'est pas un SELECT unique est refusée."""

    sql: str = Field(..., min_length=1, max_length=20_000)


def _check_tables(ast: dict[str, Any]) -> None:
    ctes: set[str] = set()
    refs: list[dict[str, Any]] = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            kind = obj.get("type")
            if kind == "TABLE_FUNCTION":
                raise SqlSandboxError("table functions are not allowed")
            if kind == "BASE_TABLE":
                refs.append(obj)
            cte_map = obj.get("cte_map")
            if isinstance(cte_map, dict):
                ctes.update(
                    str(e.get("key", "")).lower()
                    for e in cte_map.get("map", [])
                    if isinstance(e, dict)
                )
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(ast)
    for ref in refs:
        name = str(ref.get("table_name", "")).lower()
        qualified = bool(ref.get("schema_name") or ref.get("catalog_name"))
        if name in ctes and not qualified:
            continue
        if name != _INPUT or qualified:
            raise SqlSandboxError(f"only the input table '{_INPUT}' may be queried (got '{name}')")


def execute_sql_executor(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformSqlExecutorParams.model_validate(params)
    ast = parse_ast(conn, p.sql)
    validate_select_only(ast)
    _check_tables(ast)
    # Vue d'alias TEMP éphémère : la requête voit `input`, rien d'autre du pipeline. Le résultat
    # est matérialisé (TABLE) avant de retirer l'alias, un autre nœud pouvant réutiliser le nom.
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {_qi(_INPUT)} AS SELECT * FROM {_qi(input_view)}")
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS {p.sql}")
    finally:
        conn.execute(f"DROP VIEW IF EXISTS {_qi(_INPUT)}")
