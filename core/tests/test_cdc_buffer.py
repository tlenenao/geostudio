# SPDX-License-Identifier: Apache-2.0
from app.cdc.buffer import CdcBufferManager
from app.cdc.parquet_writer import ChangeRow


def _row(lsn: int) -> ChangeRow:
    return ChangeRow(op="insert", lsn=lsn, ts=0.0, pk_column="id", pk_value=lsn,
                      columns={"id": lsn}, geometry_column=None, geometry_wkb_hex=None)


def test_flush_due_on_row_count_threshold():
    mgr = CdcBufferManager()
    for i in range(500):
        mgr.add("t1", _row(i))
    assert "t1" in mgr.tables_due_for_flush()


def test_flush_not_due_below_threshold():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    assert mgr.tables_due_for_flush() == []


def test_flush_due_on_age_threshold(monkeypatch):
    times = iter([100.0, 131.0])  # opened_at capturé au 1er add, puis vérifié plus tard
    monkeypatch.setattr("app.cdc.buffer.time.monotonic", lambda: next(times))
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    assert "t1" in mgr.tables_due_for_flush()


def test_drain_empties_buffer_and_stamps_flush_ts():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    rows = mgr.drain("t1", flush_ts=42.0)
    assert [r.ts for r in rows] == [42.0]
    assert mgr.tables_due_for_flush() == []


def test_safe_ack_lsn_bounded_by_oldest_pending_across_tables():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(10))
    mgr.add("t2", _row(5))
    # t2 a un message plus ancien (lsn=5) encore non flushé : on ne peut
    # jamais accuser réception au-delà de lsn=4, même si t1 a déjà tout
    # flushé, sans quoi un crash perdrait la ligne lsn=5 de t2.
    assert mgr.safe_ack_lsn(last_seen_lsn=10) == 4


def test_safe_ack_lsn_is_last_seen_when_everything_flushed():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(10))
    mgr.drain("t1", flush_ts=0.0)
    assert mgr.safe_ack_lsn(last_seen_lsn=10) == 10
