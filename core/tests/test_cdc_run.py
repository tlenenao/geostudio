# SPDX-License-Identifier: Apache-2.0
"""AUD-123 : `app.cdc.main.run()` pilotée avec des doublures (65 lignes non couvertes)."""

import json
from contextlib import contextmanager
from types import SimpleNamespace


class _FakeBuffer:
    def __init__(self):
        self.rows: dict[str, list] = {}

    def add(self, table, row):
        self.rows.setdefault(table, []).append(row)

    def drain(self, table, *, flush_ts):
        return self.rows.pop(table, [])

    def tables_due_for_flush(self):
        return list(self.rows)

    def safe_ack_lsn(self, *, last_seen_lsn):
        return last_seen_lsn


def _scenario(monkeypatch):
    """Élection, backfill initial, backfill paresseux d'une table inconnue
    (boundary_lsn = lsn-1), table sans collection (relecture espacée), flush."""
    from app.cdc import main

    for k, v in {
        "CDC_DATABASE_URL": "postgresql://u:p@h/d",
        "S3_ENDPOINT_URL": "http://s3",
        "S3_ACCESS_KEY": "a",
        "S3_SECRET_KEY": "s",
    }.items():
        monkeypatch.setenv(k, v)

    def coll(cid, table, srid):
        return SimpleNamespace(
            id=cid,
            tenant_id="t1",
            table_name=table,
            geometry_column="geom",
            srid=srid,
            pk_column="id",
        )

    known, fresh = coll("c1", "known", 4326), coll("c2", "fresh", None)
    looked_up: list[str] = []

    class _Session:
        def scalars(self, _stmt):
            return SimpleNamespace(all=lambda: [known])

        def scalar(self, stmt):
            name = stmt.compile().params["table_name_1"]
            looked_up.append(name)
            return fresh if name == "fresh" else None

    @contextmanager
    def session_factory():
        yield _Session()

    monkeypatch.setattr(main, "make_engine", lambda url: object())
    monkeypatch.setattr(main, "make_session_factory", lambda engine: session_factory)
    monkeypatch.setattr(main.storage, "make_s3_client", lambda **kw: object())
    monkeypatch.setattr(main.storage, "ensure_cdc_bucket", lambda *a: None)
    monkeypatch.setattr(main.signal, "signal", lambda *a: None)
    monkeypatch.setattr(main.observability, "register_cdc_lag_gauge", lambda f: None)
    monkeypatch.setattr(main.election, "acquire_leadership", lambda dsn, should_stop: object())
    monkeypatch.setattr(main.election, "watch_leadership", lambda g: None)
    monkeypatch.setattr(main.consumer, "slot_wal_status", lambda dsn: "reserved")
    monkeypatch.setattr(main.consumer, "ensure_replication_slot", lambda dsn: None)
    monkeypatch.setattr(main.backfill, "current_wal_lsn", lambda s: 100)
    boundaries: list = []

    def fake_backfill(session, *, table_name, boundary_lsn, **kw):
        boundaries.append((table_name, boundary_lsn))
        return iter([f"bf-{table_name}"])

    monkeypatch.setattr(main.backfill, "iter_backfill_rows", fake_backfill)
    monkeypatch.setattr(main, "CdcBufferManager", _FakeBuffer)
    monkeypatch.setattr(
        main.consumer,
        "decode_wal2json_message",
        lambda data, **kw: (
            [SimpleNamespace(table_name="known", row="live")] if data["table"] == "known" else []
        ),
    )
    uploads: list = []
    monkeypatch.setattr(
        main,
        "_write_and_upload",
        lambda rows, **kw: uploads.append((kw["key"], list(rows), kw["srid"])),
    )

    def fake_stream(dsn, *, on_message, is_flush_due, do_flush, should_stop):
        for table, lsn in [("known", 10), ("fresh", 20), ("ghost", 30), ("ghost", 31)]:
            on_message(json.dumps({"action": "I", "table": table}), lsn)
        assert is_flush_due()
        assert do_flush() == 31

    monkeypatch.setattr(main.consumer, "stream_changes", fake_stream)
    main.run()

    return boundaries, looked_up, uploads


def test_run_end_to_end_with_stubs(monkeypatch):
    boundaries, looked_up, uploads = _scenario(monkeypatch)
    assert boundaries == [("known", 100), ("fresh", 19)]
    assert looked_up == ["fresh", "ghost"]  # 2e « ghost » dans la minute : pas relu
    by_cid = {k.split("collection_id=")[1].split("/")[0]: (r, s) for k, r, s in uploads}
    assert by_cid["c1"] == (["bf-known", "live"], 4326)
    assert by_cid["c2"] == (["bf-fresh"], 4326)  # srid None -> 4326


def test_backfill_flushes_in_segments(monkeypatch):
    """AUD-099 : le backfill est déversé par segments de _BACKFILL_FLUSH_ROWS lignes."""
    from app.cdc import main

    monkeypatch.setattr(main, "_BACKFILL_FLUSH_ROWS", 1)
    _b, _l, uploads = _scenario(monkeypatch)
    # une ligne de backfill = un segment, avant même le premier message live
    assert [rows for key, rows, _s in uploads if "collection_id=c1" in key][0] == ["bf-known"]
