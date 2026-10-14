# SPDX-License-Identifier: Apache-2.0
import threading
import time

import pytest

from app.cdc.election import acquire_leadership, watch_leadership


@pytest.fixture
def dsn(test_db_url):
    return test_db_url.replace("postgresql+psycopg://", "postgresql://")


def test_single_leader_then_takeover_on_death(dsn):
    key = 424242
    leader = acquire_leadership(dsn, key=key, poll_s=0.1)
    assert leader is not None
    # un 2e candidat ne devient pas leader tant que le 1er tient le verrou
    stop = threading.Event()
    got: list = []
    t = threading.Thread(
        target=lambda: got.append(
            acquire_leadership(dsn, key=key, poll_s=0.1, should_stop=stop.is_set)
        )
    )
    t.start()
    time.sleep(0.6)
    assert got == []
    # mort du leader -> le suiveur prend la main rapidement
    started = time.monotonic()
    leader.close()
    t.join(timeout=5)
    assert got and got[0] is not None
    assert time.monotonic() - started < 2
    got[0].close()


def test_watch_calls_on_lost_when_connection_dies(dsn):
    conn = acquire_leadership(dsn, key=424243, poll_s=0.1)
    assert conn is not None
    lost = threading.Event()
    watch_leadership(conn, on_lost=lost.set, interval_s=0.1)
    conn.close()
    assert lost.wait(2)
