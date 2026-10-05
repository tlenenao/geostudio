# SPDX-License-Identifier: Apache-2.0
"""REV-280f : lagBytes mesuré par LSN sur le slot CDC."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics import lake_lag
from app.cdc.consumer import SLOT_NAME


def test_slot_name_matches_the_cdc_consumer():
    assert lake_lag._CDC_SLOT == SLOT_NAME


def test_none_without_slot(pg_engine, monkeypatch):
    monkeypatch.setattr(lake_lag, "_CDC_SLOT", "absent_slot_b4")
    with Session(pg_engine) as s:
        assert lake_lag.lake_lag_bytes(s) is None


def test_lag_is_nonnegative_int_with_slot_and_grows(pg_engine, monkeypatch):
    name = "b4_lag_test_slot"
    monkeypatch.setattr(lake_lag, "_CDC_SLOT", name)
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        try:
            c.execute(
                text("SELECT pg_create_logical_replication_slot(:n, 'test_decoding')"), {"n": name}
            )
        except Exception:
            pytest.skip("wal_level != logical ou test_decoding indisponible")
        try:
            with Session(pg_engine) as s:
                before = lake_lag.lake_lag_bytes(s)
                assert isinstance(before, int) and before >= 0
                c.execute(text("SELECT pg_switch_wal()"))
                c.execute(text("SELECT txid_current()"))
            with Session(pg_engine) as s:
                assert lake_lag.lake_lag_bytes(s) >= before
        finally:
            c.execute(text("SELECT pg_drop_replication_slot(:n)"), {"n": name})


def test_sql_failure_gives_none(monkeypatch):
    class Boom:
        def execute(self, *a, **k):
            raise RuntimeError("denied")

        def rollback(self):
            pass

    assert lake_lag.lake_lag_bytes(Boom()) is None  # type: ignore[arg-type]
