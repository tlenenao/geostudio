# SPDX-License-Identifier: Apache-2.0
"""Mapping pur TableInfo -> contrat JSON du schéma d'une collection (spec §3).
Aucune dépendance DB ici : uniquement une transformation de données."""

from app.collections.introspection import TableInfo


def table_info_to_schema(info: TableInfo, attachment_fields: list[dict] | None = None) -> dict:
    fields = []
    for col in info.columns:
        if col.name in (info.pk_column, "tenant_id", info.geometry_column):
            continue
        entry: dict = {"name": col.name, "type": col.type, "required": col.required}
        if col.max_length is not None:
            entry["maxLength"] = col.max_length
        if col.enum_values is not None:
            entry["values"] = col.enum_values
        if col.list_item_type is not None:
            entry["itemType"] = col.list_item_type
        if col.name in info.domains:  # ARC-13 : le formulaire en tire une liste déroulante
            entry["domain"] = info.domains[col.name]
        fields.append(entry)
    for spec in attachment_fields or []:
        entry = {
            "name": spec["key"],
            "type": "attachment",
            "required": False,
            "label": spec["label"],
        }
        if spec.get("kind"):  # L8 : nature du média (image|audio|video|file)
            entry["kind"] = spec["kind"]
        fields.append(entry)
    geometry = None
    if info.geometry_column:
        geometry = {"column": info.geometry_column, "type": info.geometry_type, "srid": info.srid}
        if info.geometry_required:  # L8 : le formulaire bloque l'envoi sans géométrie
            geometry["required"] = True
    schema = {
        "collection": info.table_name,
        "pk": info.pk_column,
        "geometry": geometry,
        "fields": fields,
    }
    if info.subtypes:
        schema["subtypes"] = info.subtypes
    return schema
