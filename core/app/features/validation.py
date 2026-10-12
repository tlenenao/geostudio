# SPDX-License-Identifier: Apache-2.0
"""Validation d'un GeoJSON Feature contre le schéma introspecté (SP-3 §4).
Pur : aucune DB. Les erreurs structurées sont le contrat consommé par les
formulaires SP-4 ({"field", "code", "message"})."""

from datetime import date, datetime

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.cel_rules import constraint_errors
from app.features.rules import apply_write_rules


def _err(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _type_ok(col: ColumnInfo, value) -> bool:
    if value is None:
        return True  # l'absence de valeur relève de missing_required, pas du type
    if col.type == "string":
        return isinstance(value, str)
    if col.type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if col.type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if col.type == "boolean":
        return isinstance(value, bool)
    if col.type in ("date", "datetime"):
        if not isinstance(value, str):
            return False
        try:
            (date if col.type == "date" else datetime).fromisoformat(value)
            return True
        except ValueError:
            return False
    if col.type == "list":
        if not isinstance(value, list):
            return False
        item_col = ColumnInfo(name=col.name, type=col.list_item_type, required=False)
        return all(_type_ok(item_col, item) for item in value)
    return False  # enum géré à part ; unsupported refusé à part


def geometry_type_accepted(layer_type: str | None, geometry: dict) -> bool:
    """REV-352 : couche mixte (GEOMETRY) = tout type ; X <-> MultiX accepté (promotion
    à l'écriture par `_geometry_sql` ; MultiX sur couche X : une seule partie)."""
    gtype = geometry.get("type")
    if layer_type in (None, "GEOMETRY") or gtype == layer_type:
        return True
    if gtype == f"Multi{layer_type}":
        return len(geometry.get("coordinates") or []) == 1
    return layer_type == f"Multi{gtype}"


def _subtype_of(info: TableInfo, props: dict) -> dict | None:
    sub = info.subtypes
    if not sub:
        return None
    value = props.get(sub["field"])
    return next((i for i in sub["items"] if i["value"] == value), None)


def _effective_domain(info: TableInfo, props: dict, name: str) -> dict | None:
    """Domaine du sous-type courant s'il en déclare un pour ce champ, sinon domaine du champ ;
    la colonne de sous-type a pour domaine implicite la liste de ses sous-types."""
    sub = info.subtypes
    if sub and name == sub["field"]:
        return {"type": "list", "values": [i["value"] for i in sub["items"]]}
    item = _subtype_of(info, props)
    if item and name in item.get("domains", {}):
        return item["domains"][name]
    return info.domains.get(name)


def _outside_domain(domain: dict, value) -> bool:
    if domain["type"] == "list":
        return value not in domain["values"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    lo, hi = domain.get("min"), domain.get("max")
    return (lo is not None and value < lo) or (hi is not None and value > hi)


def _domain_message(domain: dict) -> str:
    if domain["type"] == "list":
        return f"value not in {domain['values']}"
    return f"value outside range [{domain.get('min')}, {domain.get('max')}]"


def validate_for_write(info: TableInfo, feature: dict) -> list[dict]:
    """Point d'entrée de TOUS les chemins d'écriture (REST, pipeline, import) : défauts de
    sous-type puis calculs (ARC-13/14, mutent `feature`), puis validation."""
    apply_write_rules(info, feature)
    return validate_feature(info, feature)


def validate_feature(info: TableInfo, feature: dict) -> list[dict]:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        return [_err("", "invalid_feature", "payload must be a GeoJSON Feature")]
    props_raw = feature.get("properties", {})
    if props_raw is not None and not isinstance(props_raw, dict):
        return [_err("", "invalid_feature", "payload must be a GeoJSON Feature")]

    errors: list[dict] = []
    props = props_raw or {}  # properties: null est valide (RFC 7946) → {}
    by_name = {c.name: c for c in info.columns}
    reserved = {info.pk_column, "tenant_id", info.geometry_column}

    for name, value in props.items():
        col = by_name.get(name)
        if col is None or name in reserved:
            errors.append(_err(name, "unknown_property", f"unknown property '{name}'"))
            continue
        if col.type == "unsupported":
            errors.append(
                _err(name, "unsupported_type", f"'{name}' is read-only (unsupported type)")
            )
            continue
        if col.type == "enum":
            if value is not None and value not in (col.enum_values or []):
                errors.append(_err(name, "invalid_enum", f"'{value}' not in {col.enum_values}"))
                continue
        elif not _type_ok(col, value):
            errors.append(_err(name, "invalid_type", f"expected {col.type}"))
            continue
        if value is not None and (dom := _effective_domain(info, props, name)):
            if _outside_domain(dom, value):
                errors.append(_err(name, "out_of_domain", _domain_message(dom)))

    for col in info.columns:
        if col.required and col.name not in reserved and props.get(col.name) is None:
            errors.append(_err(col.name, "missing_required", f"'{col.name}' is required"))

    geometry = feature.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append(
                _err("geometry", "geometry_mismatch", "geometry must be a GeoJSON geometry object")
            )
        elif info.geometry_column is None:
            errors.append(
                _err("geometry", "unexpected_geometry", "collection has no geometry column")
            )
        elif not geometry_type_accepted(info.geometry_type, geometry):
            errors.append(_err("geometry", "geometry_mismatch", f"expected {info.geometry_type}"))
    if not errors and info.rules:  # ARC-14 : contraintes CEL sur des valeurs déjà valides
        errors.extend(constraint_errors(info, props))
    return errors
