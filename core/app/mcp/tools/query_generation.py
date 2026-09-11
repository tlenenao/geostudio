# SPDX-License-Identifier: Apache-2.0
"""Tools MCP de génération (GAP-17) : produisent un brouillon SQL ou une
requête visuelle (filtres/jointure/résumé) depuis une question en langage
naturel — ne créent, n'écrivent, ni n'exécutent jamais rien. Le SQL généré
emprunte le même chemin d'exécution que le SQL manuel
(app.analytics.sql_sandbox.run_analyst_sql, via POST /v1/analytics/sql)
UNE FOIS validé par l'utilisateur — jamais depuis ce module."""

import json
import re

import httpx
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.copilot.egress import EgressBlockedError
from app.copilot.llm_provider import get_llm_provider
from app.db import request_scoped_session
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    require_collection_read,
    resolve_actor,
)
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege

# Bloc de code Markdown "propre" : ``` (+ langage optionnel) puis un saut de
# ligne, contenu (potentiellement multi-ligne), saut de ligne, ```. Chercher
# TOUTES les occurrences (re.DOTALL) et garder la dernière ignore toute prose
# avant/après le bloc.
_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)\n```", re.DOTALL)
# Repli pour une réponse tenant sur une seule ligne (pas de saut de ligne du
# tout autour du fence) : ```SELECT 1```.
_SINGLE_LINE_FENCE_RE = re.compile(r"```([^\n`]*)```")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    fence_matches = list(_FENCE_RE.finditer(stripped))
    if fence_matches:
        return fence_matches[-1].group(1).strip()
    single_line_matches = list(_SINGLE_LINE_FENCE_RE.finditer(stripped))
    if single_line_matches:
        return single_line_matches[-1].group(1).strip()
    return stripped


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def generate_sql_query(ctx: Context, collectionId: str, question: str) -> dict:
        """Generate a read-only SQL SELECT draft (DuckDB dialect) from a
        natural-language question, scoped to one collection. Never executes
        the query — the caller must insert it as a draft (client tool
        applySqlDraft) and the human must validate it (SQL Lab's Exécuter
        button) before it runs through POST /v1/analytics/sql. GAP-17."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            col = require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound as exc:
                raise ValueError("collection backing table not found") from exc
            except UnsupportedTable as exc:
                raise ValueError(exc.reason) from exc
            schema = table_info_to_schema(info)

        prompt = (
            "Écris une unique requête SQL SELECT (dialecte DuckDB) en "
            f'lecture seule répondant à la question, en utilisant EXACTEMENT "{collectionId}" '
            "comme nom de table dans FROM (entre guillemets doubles). N'utilise que les "
            f"colonnes listées ci-dessous. Colonnes disponibles (JSON) : {json.dumps(schema)}. "
            "Réponds uniquement par le SQL, sans aucun texte autour (un bloc de code Markdown "
            f"est toléré mais pas requis). Question : {question}"
        )
        provider = get_llm_provider()
        try:
            turn = await provider.chat(messages=[{"role": "user", "content": prompt}], tools=[])
        except EgressBlockedError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        except httpx.HTTPError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        sql = _strip_code_fence(turn.text)
        if not sql:
            raise ValueError("le fournisseur LLM n'a renvoyé aucun SQL")
        return {"sql": sql}
