# SPDX-License-Identifier: Apache-2.0
"""ARC-13 : cohérence d'une configuration domaines/sous-types avec les colonnes réelles
(pur ; le contrôle de forme est fait par les modèles Pydantic de `schemas`)."""

import dataclasses
import re

import celpy

from app.collections.introspection import TableInfo


def with_attribute_rules(info: TableInfo, col) -> TableInfo:
    """TableInfo enrichi des domaines/sous-types/règles déclarés sur la collection."""
    return dataclasses.replace(
        info,
        domains=getattr(col, "field_domains", None) or {},
        subtypes=getattr(col, "subtypes", None) or {},
        rules=getattr(col, "attribute_rules", None) or [],
        geometry_required=bool(getattr(col, "geometry_required", False)),
    )


def strip_hidden(field_domains: dict, subtypes: dict, hidden: list[str]) -> tuple[dict, dict]:
    """GAP-22 : ni domaine ni défaut d'un champ sensible n'est exposé à un lecteur masqué."""
    if not hidden:
        return field_domains, subtypes
    fd = {k: v for k, v in field_domains.items() if k not in hidden}
    if not subtypes:
        return fd, subtypes
    items = [
        {
            **i,
            "defaults": {k: v for k, v in i.get("defaults", {}).items() if k not in hidden},
            "domains": {k: v for k, v in i.get("domains", {}).items() if k not in hidden},
        }
        for i in subtypes["items"]
    ]
    return fd, {**subtypes, "items": items}


_LIST_TYPES = {"string", "integer", "number", "enum"}
_RANGE_TYPES = {"integer", "number"}


def _value_fits(col_type: str, value) -> bool:
    if col_type in ("string", "enum", "date", "datetime"):
        return isinstance(value, str)
    if col_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if col_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def check_domain_config(info: TableInfo, field_domains: dict, subtypes: dict) -> list[str]:
    """Liste de problèmes (vide = cohérent). `field_domains`/`subtypes` au format stocké."""
    cols = {
        c.name: c
        for c in info.columns
        if c.name not in (info.pk_column, "tenant_id", info.geometry_column)
    }
    problems: list[str] = []

    def check_domain(name: str, dom: dict) -> None:
        col = cols.get(name)
        if col is None:
            problems.append(f"unknown field '{name}'")
        elif dom["type"] == "list":
            # L8 : une colonne tableau (select_multiple) porte un domaine sur ses éléments.
            elem = col.list_item_type if col.type == "list" else col.type
            if elem not in _LIST_TYPES or not all(_value_fits(elem, v) for v in dom["values"]):
                problems.append(f"list domain on '{name}' does not fit type {col.type}")
        elif col.type not in _RANGE_TYPES:
            problems.append(f"range domain needs a numeric field, '{name}' is {col.type}")

    for name, dom in field_domains.items():
        check_domain(name, dom)
    if subtypes:
        sub_col = cols.get(subtypes["field"])
        if sub_col is None or sub_col.type not in ("string", "integer"):
            problems.append(f"subtype field '{subtypes['field']}' must be a string/integer column")
        for item in subtypes["items"]:
            if sub_col is not None and not _value_fits(sub_col.type, item["value"]):
                problems.append(f"subtype value {item['value']!r} does not fit '{sub_col.name}'")
            for name, value in item.get("defaults", {}).items():
                col = cols.get(name)
                if col is None:
                    problems.append(f"unknown default field '{name}'")
                elif not _value_fits(col.type, value):
                    problems.append(f"default for '{name}' does not fit type {col.type}")
            for name, dom in item.get("domains", {}).items():
                check_domain(name, dom)
    return problems


_ENV = celpy.Environment()


def cel_syntax_error(expression: str) -> str | None:
    """Message si l'expression n'est pas du CEL syntaxiquement valide, sinon None."""
    try:
        _ENV.compile(expression)
    except Exception as exc:  # CELParseError, pas de hiérarchie publique stable
        return str(exc).splitlines()[0][:200]
    return None


def check_rules_config(info: TableInfo, rules: list[dict]) -> list[str]:
    """ARC-14 : cohérence des règles avec les colonnes réelles et la syntaxe CEL."""
    reserved = (info.pk_column, "tenant_id", info.geometry_column)
    cols = {c.name for c in info.columns if c.name not in reserved}
    problems: list[str] = []
    ids = [r["id"] for r in rules]
    if len(ids) != len(set(ids)):
        problems.append("duplicate rule id(s)")
    for r in rules:
        if r["kind"] == "calculation" and r.get("field") not in cols:
            problems.append(f"rule '{r['id']}': unknown target field {r.get('field')!r}")
        elif r["kind"] == "constraint" and r.get("field") and r["field"] not in cols:
            problems.append(f"rule '{r['id']}': unknown field {r['field']!r}")
        if err := cel_syntax_error(r["expression"]):
            problems.append(f"rule '{r['id']}': invalid CEL ({err})")
    return problems


def strip_hidden_rules(rules: list[dict], hidden: list[str]) -> list[dict]:
    """GAP-22 : une règle qui cible ou lit un champ sensible est cachée aux lecteurs masqués."""
    if not hidden:
        return rules
    pat = re.compile(r"(" + "|".join(re.escape(h) for h in hidden) + r")")
    return [r for r in rules if r.get("field") not in hidden and not pat.search(r["expression"])]
