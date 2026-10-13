# SPDX-License-Identifier: Apache-2.0
"""Paramètres de run publiés d'un pipeline (ARC-K2/F3).

Un pipeline déclare `parameters: [{name, type, default, required}]` ; le
`POST /pipelines/{id}/run` (comme le webhook entrant et le tool MCP
`run_pipeline`) fournit `params`, validés ici par type. Les nœuds
référencent `{{param.nom}}` dans leurs `params`.

Jamais d'interpolation brute dans du SQL : une valeur n'atteint une
expression SQL (`expr`, `metrics`) que sous forme de LITTÉRAL TYPÉ produit
par `_sql_literal` (chaîne échappée, nombre/booléen/date revalidés) — une
valeur `x'; DROP TABLE t; --` reste donc une simple chaîne. Partout ailleurs
(chemin, collectionId…) la valeur est substituée comme donnée, sans
passage par du SQL (les compilateurs de nœud la citent eux-mêmes).

Ce module ne dépend pas de app.configs.schemas (cycle : le schéma importe
`param_refs` dans son validateur) — il manipule les objets par duck typing."""

import math
import re
from datetime import date
from typing import Any

PARAM_TYPES = ("string", "number", "integer", "boolean", "date")
_REF = re.compile(r"\{\{\s*param\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# LISTE BLANCHE des clés de params de nœud où `{{param.x}}` est admis (partout
# ailleurs : refusé à la validation de config, jamais substitué).
# - _EXPR_KEYS : expressions DuckDB bornées -> la référence devient un LITTÉRAL
#   SQL typé échappé (jamais du texte brut).
# - _DATA_KEYS : valeurs de donnée (identifiant de collection, chemin, libellé…)
#   substituées comme texte/valeur typée, que les compilateurs citent eux-mêmes.
# Exclus volontairement : `query` des readers connecteurs (SQL natif d'une base
# distante, échappement propre à chaque dialecte) et tout autre champ SQL.
_EXPR_KEYS = frozenset({"expr", "metrics", "valueExpr", "urlExpr", "headersExpr", "bodyExpr"})
_DATA_KEYS = frozenset(
    {"collectionId", "withCollectionId", "path", "key", "label", "distance", "value", "format"}
)


class PipelineParamError(ValueError):
    """Paramètre de run invalide (manquant, mal typé, inconnu) — 422 côté API."""


def param_refs(value: Any) -> set[str]:
    """Noms de paramètres référencés dans une valeur de params de nœud (récursif)."""
    if isinstance(value, str):
        return set(_REF.findall(value))
    if isinstance(value, dict):
        return set().union(*(param_refs(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(param_refs(v) for v in value)) if value else set()
    return set()


def coerce_value(name: str, ptype: str, raw: Any) -> Any:
    """Valide/convertit `raw` vers `ptype` ; lève PipelineParamError."""
    try:
        if ptype == "string":
            if not isinstance(raw, str):
                raise ValueError
            if "\x00" in raw:
                raise ValueError
            return raw
        if ptype == "boolean":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str) and raw.lower() in ("true", "false"):
                return raw.lower() == "true"
            raise ValueError
        if ptype in ("number", "integer"):
            if isinstance(raw, bool):
                raise ValueError
            if isinstance(raw, str):
                raw = float(raw) if ptype == "number" else int(raw)
            if ptype == "integer":
                if isinstance(raw, float):
                    if not raw.is_integer():
                        raise ValueError
                    raw = int(raw)
                if not isinstance(raw, int):
                    raise ValueError
                return raw
            if not isinstance(raw, int | float) or not math.isfinite(raw):
                raise ValueError
            return raw
        if ptype == "date":
            if not isinstance(raw, str):
                raise ValueError
            return date.fromisoformat(raw).isoformat()
    except (ValueError, TypeError):
        raise PipelineParamError(
            f"paramètre '{name}' : valeur invalide pour le type {ptype}"
        ) from None
    raise PipelineParamError(f"paramètre '{name}' : type inconnu {ptype!r}")


def resolve_params(declared: list, supplied: dict[str, Any] | None) -> dict[str, Any]:
    """Valeurs effectives d'un run : fournies > défaut ; requis absent, valeur
    de type incorrect ou paramètre non déclaré => PipelineParamError."""
    supplied = dict(supplied or {})
    by_name = {p.name: p for p in declared}
    unknown = sorted(set(supplied) - set(by_name))
    if unknown:
        raise PipelineParamError(f"paramètre(s) non déclaré(s) : {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for p in declared:
        if p.name in supplied and supplied[p.name] is not None:
            out[p.name] = coerce_value(p.name, p.type, supplied[p.name])
        elif p.default is not None:
            out[p.name] = coerce_value(p.name, p.type, p.default)
        elif p.required:
            raise PipelineParamError(f"paramètre requis manquant : '{p.name}'")
    return out


def _sql_literal(value: Any, ptype: str) -> str:
    if ptype == "string":
        return "'" + str(value).replace("'", "''") + "'"
    if ptype == "boolean":
        return "TRUE" if value else "FALSE"
    if ptype == "integer":
        return str(int(value))
    if ptype == "number":
        return repr(float(value))
    return f"DATE '{date.fromisoformat(value).isoformat()}'"


def _plain_text(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def _mode_for(key: str) -> str | None:
    return "sql" if key in _EXPR_KEYS else "data" if key in _DATA_KEYS else None


def misplaced_param_refs(params: Any, mode: str | None = None) -> set[str]:
    """Clés de params où une référence `{{param.x}}` est hors liste blanche."""
    if isinstance(params, str):
        return set() if mode or not _REF.search(params) else {"?"}
    if isinstance(params, list):
        return set().union(*(misplaced_param_refs(v, mode) for v in params)) if params else set()
    if isinstance(params, dict):
        bad: set[str] = set()
        for k, v in params.items():
            found = misplaced_param_refs(v, mode or _mode_for(k))
            bad |= {k} if "?" in found else found
        return bad
    return set()


def _subst(node: Any, values: dict[str, Any], types: dict[str, str], *, mode: str | None) -> Any:
    if isinstance(node, str):
        if mode is None:
            if _REF.search(node):  # défense en profondeur : la validation l'a déjà refusé
                raise PipelineParamError("paramètre référencé dans un champ non autorisé")
            return node
        sql = mode == "sql"
        whole = _REF.fullmatch(node.strip())
        if whole and not sql:
            name = whole.group(1)
            return values[name] if name in values else node

        def repl(m: re.Match) -> str:
            name = m.group(1)
            if name not in values:  # optionnel sans défaut : référence laissée telle quelle
                raise PipelineParamError(f"paramètre '{name}' référencé mais sans valeur")
            return _sql_literal(values[name], types[name]) if sql else _plain_text(values[name])

        return _REF.sub(repl, node)
    if isinstance(node, dict):
        return {k: _subst(v, values, types, mode=mode or _mode_for(k)) for k, v in node.items()}
    if isinstance(node, list):
        return [_subst(v, values, types, mode=mode) for v in node]
    return node


def apply_params(payload, values: dict[str, Any]):
    """Copie de `payload` (PipelinePayload) dont les `params` de nœud ont leurs
    `{{param.x}}` résolus. Sans paramètre déclaré, retourne `payload` tel quel."""
    declared = list(getattr(payload, "parameters", []) or [])
    if not declared:
        return payload
    types = {p.name: p.type for p in declared}
    nodes = [
        n.model_copy(update={"params": _subst(n.params, values, types, mode=None)})
        for n in payload.nodes
    ]
    return payload.model_copy(update={"nodes": nodes})
