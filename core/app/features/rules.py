# SPDX-License-Identifier: Apache-2.0
"""Règles d'attributs de collection (ARC-13 sous-types/défauts, ARC-14 règles CEL).
Pur : aucune DB ; ne lit que les attributs de l'objet Collection."""

from app.collections.introspection import TableInfo
from app.features.cel_rules import apply_calculations


def apply_write_rules(info: TableInfo, feature: dict) -> None:
    """Pose en place les défauts du sous-type courant puis les règles `calculation` (ARC-14)."""
    props = feature.get("properties")
    if not isinstance(props, dict):
        return
    if info.subtypes:
        _subtype_defaults(info, props)
    apply_calculations(info, props)


def _subtype_defaults(info: TableInfo, props: dict) -> None:
    sub = info.subtypes
    item = next((i for i in sub["items"] if i["value"] == props.get(sub["field"])), None)
    for name, value in (item or {}).get("defaults", {}).items():
        if props.get(name) is None:
            props[name] = value
