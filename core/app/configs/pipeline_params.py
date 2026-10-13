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
# Clés de params de nœud dont la valeur est une expression SQL DuckDB bornée
# (cf. app.pipelines.ops.schemas) : les références y deviennent des littéraux SQL.
_EXPR_KEYS = frozenset({"expr", "metrics"})


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


def _subst(node: Any, values: dict[str, Any], types: dict[str, str], *, sql: bool) -> Any:
    if isinstance(node, str):
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
        return {k: _subst(v, values, types, sql=sql or k in _EXPR_KEYS) for k, v in node.items()}
    if isinstance(node, list):
        return [_subst(v, values, types, sql=sql) for v in node]
    return node


def apply_params(payload, values: dict[str, Any]):
    """Copie de `payload` (PipelinePayload) dont les `params` de nœud ont leurs
    `{{param.x}}` résolus. Sans paramètre déclaré, retourne `payload` tel quel."""
    declared = list(getattr(payload, "parameters", []) or [])
    if not declared:
        return payload
    types = {p.name: p.type for p in declared}
    nodes = [
        n.model_copy(update={"params": _subst(n.params, values, types, sql=False)})
        for n in payload.nodes
    ]
    return payload.model_copy(update={"nodes": nodes})
