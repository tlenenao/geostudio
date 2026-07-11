"""Introspection réelle : information_schema + geometry_columns + pg_enum.
Toutes les requêtes sont paramétrées — le nom de table est une *valeur* ici,
jamais un identifiant interpolé."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.introspection import (
    ColumnInfo, FieldType, TableInfo, TableNotFound, UnsupportedTable,
)

_TYPE_MAP: dict[str, FieldType] = {
    "text": "string", "character varying": "string", "character": "string",
    "integer": "integer", "bigint": "integer", "smallint": "integer",
    "numeric": "number", "double precision": "number", "real": "number",
    "boolean": "boolean", "date": "date",
    "timestamp with time zone": "datetime", "timestamp without time zone": "datetime",
}

_GEOM_TYPES = {
    "POINT": "Point", "LINESTRING": "LineString", "POLYGON": "Polygon",
    "MULTIPOINT": "MultiPoint", "MULTILINESTRING": "MultiLineString",
    "MULTIPOLYGON": "MultiPolygon",
}


def introspect_table(session: Session, table_name: str) -> TableInfo:
    exists = session.execute(text(
        "SELECT relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = :t"
    ), {"t": table_name}).scalar()
    if exists is None:
        raise TableNotFound(table_name)
    if exists != "r":  # vue, matview, foreign table…
        raise UnsupportedTable("only plain tables can be registered")

    pk_rows = session.execute(text(
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass AND i.indisprimary"
    ), {"t": table_name}).scalars().all()
    if len(pk_rows) == 0:
        raise UnsupportedTable("table has no primary key")
    if len(pk_rows) > 1:
        raise UnsupportedTable("composite primary keys are not supported")
    pk_column = pk_rows[0]

    geom_rows = session.execute(text(
        "SELECT f_geometry_column, type, srid FROM geometry_columns "
        "WHERE f_table_schema = 'public' AND f_table_name = :t"
    ), {"t": table_name}).all()
    if len(geom_rows) > 1:
        raise UnsupportedTable("multiple geometry columns are not supported")
    geometry_column = geometry_type = srid = None
    if geom_rows:
        geometry_column = geom_rows[0][0]
        # geometry_columns renvoie le type en MAJUSCULES ("POINT") ; on normalise
        # vers la casse GeoJSON via une table de correspondance explicite.
        raw = geom_rows[0][1]
        geometry_type = _GEOM_TYPES.get(raw, raw)
        srid = geom_rows[0][2]

    col_rows = session.execute(text(
        "SELECT column_name, data_type, udt_name, udt_schema, is_nullable, column_default, "
        "character_maximum_length, is_identity "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
    ), {"t": table_name}).all()

    columns: list[ColumnInfo] = []
    for name, data_type, udt_name, udt_schema, is_nullable, default, max_len, is_identity in col_rows:
        if name == geometry_column:
            continue
        enum_values = None
        if data_type == "USER-DEFINED":
            enum_values = session.execute(text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE t.typname = :ty AND n.nspname = :ns "
                "ORDER BY e.enumsortorder"
            ), {"ty": udt_name, "ns": udt_schema}).scalars().all()
            ftype: FieldType = "enum" if enum_values else "unsupported"
            enum_values = list(enum_values) or None
        else:
            ftype = _TYPE_MAP.get(data_type, "unsupported")
        required = (
            is_nullable == "NO" and default is None and is_identity != "YES"
        )
        columns.append(ColumnInfo(name=name, type=ftype, required=required,
                                  max_length=max_len, enum_values=enum_values))

    return TableInfo(table_name=table_name, pk_column=pk_column,
                     geometry_column=geometry_column, geometry_type=geometry_type,
                     srid=srid, columns=columns)
