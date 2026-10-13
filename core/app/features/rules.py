# SPDX-License-Identifier: Apache-2.0
"""Règles d'attributs de collection (ARC-13 sous-types/défauts, ARC-14 règles CEL).
Pur : aucune DB ; ne lit que les attributs de l'objet Collection."""

import dataclasses

from app.collections.introspection import TableInfo
from app.features.cel_rules import apply_calculations


def apply_write_rules(info: TableInfo, feature: dict) -> None:
    """Pose en place les défauts du sous-type courant puis les règles `calculation` (ARC-14).
    Une cible absente de `info.columns` (champ sensible retiré pour un écrivain masqué,
    colonne supprimée) est ignorée : jamais d'`unknown_property` qui fuirait son nom."""
    props = feature.get("properties")
    if not isinstance(props, dict):
        return
    cols = {c.name for c in info.columns}
    if info.subtypes:
        _subtype_defaults(info, props, cols)
    rules = [r for r in info.rules if r["kind"] != "calculation" or r["field"] in cols]
    apply_calculations(dataclasses.replace(info, rules=rules), props)


def _subtype_defaults(info: TableInfo, props: dict, cols: set[str]) -> None:
    sub = info.subtypes
    item = next((i for i in sub["items"] if i["value"] == props.get(sub["field"])), None)
    for name, value in (item or {}).get("defaults", {}).items():
        if name in cols and props.get(name) is None:
            props[name] = value
