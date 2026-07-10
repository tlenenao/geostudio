"""Mapping pur TableInfo -> contrat JSON du schéma d'une collection (spec §3).
Aucune dépendance DB ici : uniquement une transformation de données."""
from app.collections.introspection import TableInfo


def table_info_to_schema(info: TableInfo) -> dict:
    fields = []
    for col in info.columns:
        if col.name in (info.pk_column, "tenant_id", info.geometry_column):
            continue
        entry: dict = {"name": col.name, "type": col.type, "required": col.required}
        if col.max_length is not None:
            entry["maxLength"] = col.max_length
        if col.enum_values is not None:
            entry["values"] = col.enum_values
        fields.append(entry)
    geometry = None
    if info.geometry_column:
        geometry = {"column": info.geometry_column, "type": info.geometry_type,
                    "srid": info.srid}
    return {"collection": info.table_name, "pk": info.pk_column,
            "geometry": geometry, "fields": fields}
