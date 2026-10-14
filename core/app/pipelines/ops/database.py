# SPDX-License-Identifier: Apache-2.0
"""Famille Database (ARC vague 4, voie M, F8) : `transform.sqlExecutor`.

SQL **en lecture seule** sur les données du flux (qui vient du lac via reader.collection, donc
déjà sous RLS/masquage/limites géographiques) : un unique SELECT, qui ne voit que l'entrée sous
le nom `input`. Réutilise les primitives AST de la sandbox SQL-analyste ; la vraie frontière de
sécurité reste la connexion DuckDB verrouillée du runtime (`enable_external_access=false`), ces
contrôles rejettent tôt DROP/ATTACH/COPY/INSERT, les tables étrangères et les fonctions-tables."""

import os
import threading
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only
from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi

_INPUT = "input"
# Durée max de la requête (CTE récursive sans arrêt, produit cartésien). Mémoire (2 Go) et disque
# temporaire (5 Go) sont déjà bornés par open_connection() sur l'aperçu ET le run ; le temps ne
# l'est que sur l'aperçu (timer de runtime.preview_pipeline), d'où ce timer propre à l'op.
_TIMEOUT_S = float(os.environ.get("CORE_SQL_EXECUTOR_TIMEOUT_S") or 60)


class TransformSqlExecutorParams(BaseModel):
    """Exécute une requête SQL SELECT (lecture seule) sur l'entrée, nommée `input` dans la
    requête. Le résultat devient le flux de sortie : garder la colonne `geometry` pour la suite
    d'un pipeline spatial. Toute instruction qui n'est pas un SELECT unique est refusée."""

    sql: str = Field(..., min_length=1, max_length=20_000)


def _existing_names(conn) -> set[str]:
    return {
        str(r[0]).lower()
        for r in conn.execute(
            "SELECT table_name FROM duckdb_tables() UNION SELECT view_name FROM duckdb_views()"
        ).fetchall()
    }


def _check_tables(conn, ast: dict[str, Any]) -> None:
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
    # Une CTE ne doit pas porter le nom d'un objet existant (vue d'un autre nœud) :
    # `WITH n1 AS (SELECT * FROM n1)` relirait cet objet par la porte de derrière.
    shadowed = ctes & (_existing_names(conn) - {_INPUT})
    if shadowed:
        raise SqlSandboxError(f"CTE name(s) {sorted(shadowed)} collide with pipeline objects")
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
    _check_tables(conn, ast)
    # Vue d'alias TEMP éphémère : la requête voit `input`, rien d'autre du pipeline. Le résultat
    # est matérialisé (TABLE) avant de retirer l'alias, un autre nœud pouvant réutiliser le nom.
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {_qi(_INPUT)} AS SELECT * FROM {_qi(input_view)}")
    timer = threading.Timer(_TIMEOUT_S, conn.interrupt)
    timer.daemon = True
    timer.start()
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS {p.sql}")
    except duckdb.InterruptException as exc:
        raise PipelineRuntimeError("transform.sqlExecutor: query exceeded the time limit") from exc
    finally:
        timer.cancel()
        conn.execute(f"DROP VIEW IF EXISTS {_qi(_INPUT)}")
