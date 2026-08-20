# SPDX-License-Identifier: Apache-2.0
from app.collections.introspection import ColumnInfo, TableInfo
from app.collections.schema_json import table_info_to_schema


def _info(columns):
    return TableInfo(
        table_name="incidents",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=columns,
    )


def test_schema_shape():
    schema = table_info_to_schema(
        _info(
            [
                ColumnInfo(name="titre", type="string", required=True, max_length=200),
                ColumnInfo(
                    name="gravite",
                    type="enum",
                    required=False,
                    enum_values=["faible", "moyenne", "haute"],
                ),
            ]
        )
    )
    assert schema == {
        "collection": "incidents",
        "pk": "id",
        "geometry": {"column": "geom", "type": "Point", "srid": 4326},
        "fields": [
            {"name": "titre", "type": "string", "required": True, "maxLength": 200},
            {
                "name": "gravite",
                "type": "enum",
                "required": False,
                "values": ["faible", "moyenne", "haute"],
            },
        ],
    }


def test_pk_and_tenant_id_excluded():
    schema = table_info_to_schema(
        _info(
            [
                ColumnInfo(name="id", type="integer", required=False),
                ColumnInfo(name="tenant_id", type="string", required=True),
                ColumnInfo(name="titre", type="string", required=True),
            ]
        )
    )
    assert [f["name"] for f in schema["fields"]] == ["titre"]


def test_no_geometry():
    info = TableInfo(
        table_name="notes",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
        columns=[ColumnInfo(name="txt", type="string", required=False)],
    )
    assert table_info_to_schema(info)["geometry"] is None
