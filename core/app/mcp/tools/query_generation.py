# SPDX-License-Identifier: Apache-2.0
"""Tools MCP de génération (GAP-17, REV-183) : produisent un brouillon SQL, CEL ou une
requête visuelle (filtres/jointure/résumé) depuis une question en langage
naturel — ne créent, n'écrivent, ni n'exécutent jamais rien. Le SQL généré
emprunte le même chemin d'exécution que le SQL manuel
(app.analytics.sql_sandbox.run_analyst_sql, via POST /v1/analytics/sql)
UNE FOIS validé par l'utilisateur — jamais depuis ce module."""

import json
import re
from typing import Literal

import httpx
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ValidationError, model_validator

from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs.document_validation import _cel_syntax_error
from app.copilot.egress import EgressBlockedError
from app.copilot.llm_provider import get_llm_provider
from app.db import request_scoped_session
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    require_access,
    require_collection_read,
    resolve_actor,
    visible_table_info,
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


# REV-183/303 : références de champ CEL d'un brouillon (vars.x, record.x,
# user.x, ctx.x), aussi sous les formes `vars . x`, `vars\n.x`, `vars["x"]`,
# `record['x']`, chaînées (`vars["a"]["b"]`, `vars.a.b`). Toute référence absente
# de availableFields est refusée : le modèle ne doit pas inventer de variable.
# Un accès par crochets à clé non littérale (`vars[x]`, y compris en queue de
# chaîne) est refusé car invérifiable. REV-303a : un littéral de chaîne isolé
# n'est jamais une référence (l'alternative `_STR` le consomme en premier) ;
# seule une chaîne en position d'index (`vars["x"]`) en est une.
# Une chaîne brute CEL (r"..", R'..') n'a pas d'échappement : `r"\"` est complète.
_STR = r"""(?<!\w)[rR]"[^"]*"|(?<!\w)[rR]'[^']*'|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'"""
_CEL_REF_RE = re.compile(
    rf"""(?P<str>{_STR})|\b(?P<root>vars|record|user|ctx)\s*(?:\.\s*(?P<dot>[A-Za-z_]\w*)|\[\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<other>[^\]]*))\])|(?<![.\w])(?P<bare>vars|record|user|ctx)\b"""
)
_CEL_TAIL_RE = re.compile(r"""\s*\[\s*(?:"[^"]*"|'[^']*')\s*\]|\s*\.\s*\w+|\s*\[[^\]]*\]""")


def _cel_refs(
    expression: str, roots: frozenset[str] = frozenset({"vars", "record", "user", "ctx"})
) -> set[str]:
    refs: set[str] = set()
    pos = 0
    while m := _CEL_REF_RE.search(expression, pos):
        pos = m.end()
        if m.group("str") is not None:
            continue
        if bare := m.group("bare"):  # racine nue (`size(vars)`) : invérifiable
            refs.add(f"{bare} (racine nue)")
            if bare not in roots:
                refs.add(f"{bare} (racine non autorisée)")
            continue
        root = m.group("root")
        member = m.group("dot") or m.group("dq") or m.group("sq")
        if m.group("other") is not None and not member:
            refs.add(f"{root}[…]")
        else:
            refs.add(f"{root}.{member}")
        if root not in roots:
            refs.add(f"{root} (racine non autorisée)")
        # queue chaînée : chaque indexation non littérale est invérifiable.
        while t := _CEL_TAIL_RE.match(expression, pos):
            pos = t.end()
            seg = t.group(0).strip()
            if seg.startswith("[") and not re.fullmatch(
                r"""\[\s*("[^"]*"|'[^']*'|\d+)\s*\]""", seg
            ):
                refs.add(f"{root}[…]")
    return refs


CelContext = Literal["visibleWhen", "computedColumn", "actionCondition", "binding"]
_CEL_CONTEXT_ROOTS: dict[str, frozenset[str]] = {
    "visibleWhen": frozenset({"vars", "user"}),
    "binding": frozenset({"vars", "user"}),
    "computedColumn": frozenset({"record", "vars", "user"}),
    "actionCondition": frozenset({"vars", "user", "ctx", "record"}),
}
_CEL_CONTEXT_PROMPTS: dict[str, str] = {
    "visibleWhen": "Écris une unique expression CEL booléenne (Common Expression Language) "
    "servant de condition d'affichage d'un widget.",
    "computedColumn": "Écris une unique expression CEL (Common Expression Language) "
    "calculant la valeur d'une colonne calculée à partir de l'enregistrement `record`.",
    "actionCondition": "Écris une unique expression CEL booléenne (Common Expression Language) "
    "servant de condition d'exécution d'une action.",
    "binding": "Écris une unique expression CEL (Common Expression Language) "
    "servant de liaison dynamique (binding) d'une propriété de widget.",
}

_MAX_CEL_QUESTION_CHARS = 2000
_MAX_CEL_FIELDS = 200


class GeneratedFilterRow(BaseModel):
    column: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains"]
    value: str


class GeneratedJoin(BaseModel):
    collectionId: str
    on: str
    how: Literal["inner", "left"]


class GeneratedMetric(BaseModel):
    alias: str
    function: Literal[
        "count", "countDistinct", "sum", "avg", "median", "percentile", "stddev", "min", "max"
    ]
    sourceColumn: str | None = None
    p: float | None = None

    @model_validator(mode="after")
    def _check_function_arity(self) -> "GeneratedMetric":
        # M2 (revue finale de branche GAP-17) : mêmes règles que le
        # validateur client `isValidGeneratedMetric`
        # (shell/src/builder/copilot/applyVisualQueryClientOp.ts), qui les
        # tient lui-même de `metricExpr`/`decompileMetrics`
        # (compilePipeline.ts) — `count` compile en count(*) et n'a jamais de
        # colonne source, toute autre fonction en exige une (quoteIdent la
        # cite dans le SQL émis), et `p` n'a de sens que pour `percentile`,
        # sur l'intervalle OUVERT (0, 100). Sans ce contrôle ici, une
        # métrique mal formée traversait le cœur sans erreur et n'était
        # abandonnée qu'en silence côté shell — le modèle n'en savait rien et
        # ne pouvait pas retenter.
        if self.function == "count":
            if self.sourceColumn is not None:
                raise ValueError("la métrique 'count' ne prend pas de sourceColumn")
        elif self.sourceColumn is None:
            raise ValueError(f"la métrique '{self.function}' exige un sourceColumn")
        if self.function == "percentile":
            if self.p is None or not (0 < self.p < 100):
                raise ValueError("la métrique 'percentile' exige un p tel que 0 < p < 100")
        elif self.p is not None:
            raise ValueError(f"la métrique '{self.function}' ne prend pas de p")
        return self


class GeneratedSummary(BaseModel):
    groupBy: list[str] = []
    metrics: list[GeneratedMetric] = []


class GeneratedVisualQuery(BaseModel):
    filters: list[GeneratedFilterRow] = []
    join: GeneratedJoin | None = None
    summary: GeneratedSummary | None = None


def _known_field_names(schema: dict, joined_schema: dict | None) -> set[str]:
    names = {f["name"] for f in schema["fields"]}
    if joined_schema:
        base_names = names
        for f in joined_schema["fields"]:
            names.add(f["name"] if f["name"] not in base_names else f"joined_{f['name']}")
    return names


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def generate_sql_query(ctx: Context, collectionId: str, question: str) -> dict:
        """Generate a read-only SQL SELECT draft (DuckDB dialect) from a
        natural-language question, scoped to one collection. Never executes
        the query — the caller must insert it as a draft (client tool
        applySqlDraft) and the human must validate it (SQL Lab's Exécuter
        button) before it runs through POST /v1/analytics/sql. GAP-17.

        Schema source ≠ execution source (M4, revue finale de branche
        GAP-17) : the column list comes from a live PostGIS introspection of
        the collection's table, while the drafted SQL later executes against
        the GeoParquet lakehouse (run_analyst_sql materialises CDC-replicated
        files). For a collection CDC has not replicated yet, this tool will
        confidently draft valid-looking SQL that fails at execution time with
        "collection '<id>' has no data yet"."""
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
            schema = table_info_to_schema(visible_table_info(session, user, col, info))

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

    @server.tool()
    async def generate_visual_query(
        ctx: Context, baseCollectionId: str, question: str, joinCollectionId: str | None = None
    ) -> dict:
        """Generate structured filters/join/summary (matching the visual
        query wizard's FilterRow[]/JoinConfig/SummaryConfig shapes) from a
        natural-language question — never creates or executes anything.
        The caller must apply the result via the client tool
        applyVisualQueryDraft; the human must validate the wizard form
        before any pipeline is created/run. GAP-17."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            col = require_collection_read(session, user=user, collection_id=baseCollectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound as exc:
                raise ValueError("collection backing table not found") from exc
            except UnsupportedTable as exc:
                raise ValueError(exc.reason) from exc
            schema = table_info_to_schema(visible_table_info(session, user, col, info))

            joined_schema = None
            if joinCollectionId:
                joined_col = require_collection_read(
                    session, user=user, collection_id=joinCollectionId
                )
                try:
                    joined_info = introspect_table(session, joined_col.table_name)
                except TableNotFound as exc:
                    raise ValueError("joined collection backing table not found") from exc
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason) from exc
                joined_schema = table_info_to_schema(
                    visible_table_info(session, user, joined_col, joined_info)
                )

        prompt = (
            "Réponds UNIQUEMENT par un objet JSON de la forme "
            '{"filters": [...], "join": null | {...}, "summary": null | {...}}. '
            'Chaque filtre : {"column": str, "operator": '
            '"eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"contains", "value": str}. '
            'La jointure (ou null) : {"collectionId": str, "on": str, '
            '"how": "inner"|"left"}. Le résumé (ou null) : {"groupBy": [str], '
            '"metrics": [{"alias": str, "function": '
            '"count"|"countDistinct"|"sum"|"avg"|"median"|"percentile"|"stddev"|"min"|"max", '
            '"sourceColumn": str|null, "p": number|null}]} — "p" uniquement pour '
            '"percentile" (0 < p < 100), sinon null. '
            f"Schéma de la collection de base : {json.dumps(schema)}. "
            + (
                f"Schéma de la collection jointe : {json.dumps(joined_schema)}. "
                if joined_schema
                else ""
            )
            + f"Question : {question}"
        )
        provider = get_llm_provider()
        try:
            turn = await provider.chat(messages=[{"role": "user", "content": prompt}], tools=[])
        except EgressBlockedError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        except httpx.HTTPError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        cleaned = _strip_code_fence(turn.text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"réponse LLM non-JSON : {exc}") from exc
        try:
            generated = GeneratedVisualQuery.model_validate(parsed)
        except ValidationError as exc:
            raise ValueError(f"réponse LLM mal formée : {exc.error_count()} erreur(s)") from exc

        known = _known_field_names(schema, joined_schema)
        for row in generated.filters:
            if row.column not in known:
                raise ValueError(f"colonne inconnue référencée par un filtre : {row.column!r}")
        if generated.summary:
            for name in generated.summary.groupBy:
                if name not in known:
                    raise ValueError(f"colonne inconnue référencée par groupBy : {name!r}")
            for metric in generated.summary.metrics:
                if metric.sourceColumn is not None and metric.sourceColumn not in known:
                    raise ValueError(
                        f"colonne inconnue référencée par une métrique : {metric.sourceColumn!r}"
                    )

        return generated.model_dump()

    @server.tool()
    async def generate_cel_expression(
        ctx: Context,
        itemId: str,
        question: str,
        availableFields: list[str],
        context: CelContext = "visibleWhen",
    ) -> dict:
        """Generate a CEL expression draft from a natural-language question,
        for the given context (visibleWhen, computedColumn, actionCondition,
        binding). Only the references listed in availableFields (e.g.
        "vars.statut", "user.name", "record.population") may appear in it.
        Never writes anything: the caller inserts the
        draft with the client tool applyCelDraft and the human applies it. REV-183."""
        if len(question) > _MAX_CEL_QUESTION_CHARS:
            raise ValueError("question trop longue (2000 caractères maximum)")
        if len(availableFields) > _MAX_CEL_FIELDS:
            raise ValueError("trop de champs disponibles (200 maximum)")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=itemId, action="write")

        prompt = (
            f"{_CEL_CONTEXT_PROMPTS[context]} N'utilise QUE les références "
            f"suivantes (JSON) : {json.dumps(availableFields)}. Réponds uniquement par "
            "l'expression, sans aucun texte autour (un bloc de code Markdown est toléré "
            f"mais pas requis). Question : {question}"
        )
        provider = get_llm_provider()
        try:
            turn = await provider.chat(messages=[{"role": "user", "content": prompt}], tools=[])
        except EgressBlockedError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        except httpx.HTTPError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        expression = _strip_code_fence(turn.text)
        if not expression:
            raise ValueError("le fournisseur LLM n'a renvoyé aucune expression")
        if error := _cel_syntax_error(expression):
            raise ValueError(f"expression CEL invalide : {error}")
        unknown = sorted(_cel_refs(expression, _CEL_CONTEXT_ROOTS[context]) - set(availableFields))
        if unknown:
            raise ValueError(f"champs inconnus dans l'expression : {', '.join(unknown)}")
        return {"expression": expression}
