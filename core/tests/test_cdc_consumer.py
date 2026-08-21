# SPDX-License-Identifier: Apache-2.0
import json

from app.cdc.consumer import decode_wal2json_message

_INSERT_PAYLOAD = json.dumps(
    {
        "change": [
            {
                "kind": "insert",
                "table": "t_rls",
                "columnnames": ["id", "titre", "geom"],
                "columnvalues": [1, "a", "0101000020E6100000..."],
            }
        ]
    }
)

_DELETE_PAYLOAD = json.dumps(
    {
        "change": [
            {
                "kind": "delete",
                "table": "t_rls",
                "oldkeys": {"keynames": ["id"], "keyvalues": [1]},
            }
        ]
    }
)

_MULTI_CHANGE_PAYLOAD = json.dumps(
    {
        "change": [
            {
                "kind": "insert",
                "table": "t_rls",
                "columnnames": ["id", "titre"],
                "columnvalues": [2, "b"],
            },
            {
                "kind": "update",
                "table": "t_rls",
                "columnnames": ["id", "titre"],
                "columnvalues": [2, "c"],
            },
        ]
    }
)

_UNKNOWN_TABLE_PAYLOAD = json.dumps(
    {
        "change": [
            {"kind": "insert", "table": "not_tracked", "columnnames": ["id"], "columnvalues": [1]}
        ]
    }
)

_META = {"t_rls": ("id", "geom")}


def test_decode_insert_extracts_geometry_and_columns():
    decoded = decode_wal2json_message(_INSERT_PAYLOAD, lsn=100, collection_meta=_META)
    assert len(decoded) == 1
    row = decoded[0].row
    assert decoded[0].table_name == "t_rls"
    assert row.op == "insert"
    assert row.lsn == 100
    assert row.pk_value == 1
    assert row.geometry_wkb_hex == "0101000020E6100000..."
    assert "geom" not in row.columns  # extraite dans geometry_wkb_hex, pas dupliquée


def test_decode_delete_is_tombstone_from_oldkeys():
    decoded = decode_wal2json_message(_DELETE_PAYLOAD, lsn=200, collection_meta=_META)
    row = decoded[0].row
    assert row.op == "delete"
    assert row.pk_value == 1
    assert row.columns == {"id": 1}
    assert row.geometry_wkb_hex is None


def test_decode_message_with_multiple_changes():
    decoded = decode_wal2json_message(_MULTI_CHANGE_PAYLOAD, lsn=300, collection_meta=_META)
    assert [d.row.op for d in decoded] == ["insert", "update"]
    assert all(d.row.lsn == 300 for d in decoded)  # même LSN de message, suffisant pour max(_lsn)


def test_decode_ignores_unknown_table():
    decoded = decode_wal2json_message(_UNKNOWN_TABLE_PAYLOAD, lsn=400, collection_meta=_META)
    assert decoded == []
