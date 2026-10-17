# SPDX-License-Identifier: Apache-2.0
"""Décodage wal2json format-version 2 (AUD-012) : un message = un changement."""

import json

import pytest

from app.cdc import consumer
from app.cdc.consumer import decode_wal2json_message


def _cols(**values):
    return [{"name": k, "type": "unknown", "value": v} for k, v in values.items()]


_INSERT_PAYLOAD = json.dumps(
    {
        "action": "I",
        "schema": "public",
        "table": "t_rls",
        "columns": _cols(id=1, titre="a", geom="0101000020E6100000..."),
    }
)
_UPDATE_PAYLOAD = json.dumps(
    {"action": "U", "schema": "public", "table": "t_rls", "columns": _cols(id=2, titre="c")}
)
_DELETE_PAYLOAD = json.dumps(
    {"action": "D", "schema": "public", "table": "t_rls", "identity": _cols(id=1)}
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


def test_decode_update():
    (decoded,) = decode_wal2json_message(_UPDATE_PAYLOAD, lsn=300, collection_meta=_META)
    assert (decoded.row.op, decoded.row.columns) == ("update", {"id": 2, "titre": "c"})


def test_decode_delete_is_tombstone_from_identity():
    decoded = decode_wal2json_message(_DELETE_PAYLOAD, lsn=200, collection_meta=_META)
    row = decoded[0].row
    assert row.op == "delete"
    assert row.pk_value == 1
    assert row.columns == {"id": 1}
    assert row.geometry_wkb_hex is None


def test_decode_ignores_transaction_markers_messages_and_truncate():
    for action in ("B", "C", "M", "T"):
        payload = {"action": action, "schema": "public", "table": "t_rls"}
        assert decode_wal2json_message(payload, lsn=1, collection_meta=_META) == []


def test_decode_ignores_unknown_table():
    payload = {"action": "I", "schema": "public", "table": "not_tracked", "columns": _cols(id=1)}
    assert decode_wal2json_message(payload, lsn=400, collection_meta=_META) == []


def test_decode_accepts_an_already_decoded_message():
    # REV-364 h : le worker décode le JSON une fois et le passe tel quel.
    from_str = decode_wal2json_message(_INSERT_PAYLOAD, lsn=100, collection_meta=_META)
    from_dict = decode_wal2json_message(json.loads(_INSERT_PAYLOAD), lsn=100, collection_meta=_META)
    assert from_dict == from_str


class _FakeCur:
    def __init__(self, calls):
        self.calls = calls

    def create_replication_slot(self, name, output_plugin):
        self.calls.append(("create", name, output_plugin))

    def close(self):
        pass


class _FakeConn:
    def close(self):
        pass


def test_lost_slot_is_dropped_then_recreated(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: "lost")
    monkeypatch.setattr(consumer, "_drop_slot", lambda dsn: calls.append("drop"))
    monkeypatch.setattr(consumer, "_connect", lambda dsn: (_FakeConn(), _FakeCur(calls)))
    assert consumer.ensure_replication_slot("dsn") is True
    assert calls == ["drop", ("create", consumer.SLOT_NAME, "wal2json")]


def test_healthy_slot_is_kept_without_replication_connection(monkeypatch):
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: "reserved")

    def _no_connect(dsn):
        pytest.fail("aucune connexion de réplication attendue")

    monkeypatch.setattr(consumer, "_connect", _no_connect)
    assert consumer.ensure_replication_slot("dsn") is False


def test_absent_slot_is_created(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: None)
    monkeypatch.setattr(consumer, "_connect", lambda dsn: (_FakeConn(), _FakeCur(calls)))
    assert consumer.ensure_replication_slot("dsn") is True
    assert calls == [("create", consumer.SLOT_NAME, "wal2json")]
