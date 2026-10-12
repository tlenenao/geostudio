# SPDX-License-Identifier: Apache-2.0
"""Évaluation serveur des règles d'attributs CEL (ARC-14, ADR 0006 : cel-python côté serveur).

Les propriétés de l'entité sont liées comme variables CEL de même nom que la colonne
(`surface > 0.0`). Une colonne absente ou nulle vaut `null` : une comparaison sur `null` est une
erreur CEL, traitée comme « règle non applicable » (jamais comme une violation) pour que
l'optionnel ne soit pas confondu avec l'invalide (l'obligatoire relève de `missing_required`)."""

from functools import lru_cache
from typing import Any

import celpy
from celpy import celtypes
from celpy.evaluation import CELEvalError

from app.collections.domains import cel_syntax_error  # noqa: F401  (ré-export)
from app.collections.introspection import TableInfo

_ENV = celpy.Environment()


class RuleNotApplicable(Exception):
    """L'expression ne s'évalue pas sur cette entité (opérande nul, type inattendu…)."""


@lru_cache(maxsize=512)
def _program(expression: str):
    return _ENV.program(_ENV.compile(expression))


def _to_py(value: Any) -> Any:
    if isinstance(value, celtypes.BoolType):
        return bool(value)
    if isinstance(value, (celtypes.IntType, celtypes.UintType)):
        return int(value)
    if isinstance(value, celtypes.DoubleType):
        return float(value)
    if isinstance(value, celtypes.StringType):
        return str(value)
    if isinstance(value, (celtypes.ListType, list)):
        return [_to_py(v) for v in value]
    if isinstance(value, (celtypes.MapType, dict)):
        return {str(k): _to_py(v) for k, v in value.items()}
    return value


def evaluate(info: TableInfo, expression: str, props: dict) -> Any:
    """Valeur Python de l'expression sur `props`. Lève RuleNotApplicable si non évaluable."""
    activation = {c.name: None for c in info.columns}
    activation.update(props)
    try:
        result = _program(expression).evaluate(
            {k: celpy.json_to_cel(v) for k, v in activation.items()}
        )
    except (CELEvalError, TypeError, ValueError, KeyError) as exc:
        raise RuleNotApplicable(str(exc)) from exc
    if isinstance(result, CELEvalError):  # celpy renvoie parfois l'erreur au lieu de la lever
        raise RuleNotApplicable(str(result))
    return _to_py(result)


def constraint_errors(info: TableInfo, props: dict) -> list[dict]:
    """Erreurs {field, code, message} des règles `constraint` (celles `batch` ne s'évaluent
    qu'en job) violées par `props`."""
    errors = []
    for rule in info.rules:
        if rule["kind"] != "constraint":
            continue
        try:
            ok = evaluate(info, rule["expression"], props)
        except RuleNotApplicable:
            continue
        if ok is False:
            errors.append(
                {
                    "field": rule.get("field") or "",
                    "code": "constraint_violation",
                    "message": rule["message"],
                }
            )
    return errors


def apply_calculations(info: TableInfo, props: dict) -> None:
    """Pose en place les résultats des règles `calculation`, dans l'ordre de déclaration :
    `default` seulement si le champ est absent/nul, `derived` toujours."""
    for rule in info.rules:
        if rule["kind"] != "calculation":
            continue
        name = rule["field"]
        if rule.get("mode", "default") == "default" and props.get(name) is not None:
            continue
        try:
            value = evaluate(info, rule["expression"], props)
        except RuleNotApplicable:
            continue
        if value is not None:
            props[name] = value
