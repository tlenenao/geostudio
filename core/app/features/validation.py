# SPDX-License-Identifier: Apache-2.0
"""Validation d'un GeoJSON Feature contre le schéma introspecté (SP-3 §4).
Pur : aucune DB. Les erreurs structurées sont le contrat consommé par les
formulaires SP-4 ({"field", "code", "message"})."""
from datetime import date, datetime

from app.collections.introspection import ColumnInfo, TableInfo


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
    return False  # enum géré à part ; unsupported refusé à part


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
            errors.append(_err(name, "unsupported_type",
                               f"'{name}' is read-only (unsupported type)"))
            continue
        if col.type == "enum":
            if value is not None and value not in (col.enum_values or []):
                errors.append(_err(name, "invalid_enum",
                                   f"'{value}' not in {col.enum_values}"))
            continue
        if not _type_ok(col, value):
            errors.append(_err(name, "invalid_type", f"expected {col.type}"))

    for col in info.columns:
        if col.required and props.get(col.name) is None:
            errors.append(_err(col.name, "missing_required", f"'{col.name}' is required"))

    geometry = feature.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append(_err("geometry", "geometry_mismatch",
                               "geometry must be a GeoJSON geometry object"))
        elif info.geometry_column is None:
            errors.append(_err("geometry", "unexpected_geometry",
                               "collection has no geometry column"))
        elif geometry.get("type") != info.geometry_type:
            errors.append(_err("geometry", "geometry_mismatch",
                               f"expected {info.geometry_type}"))
    return errors
