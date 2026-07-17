# SPDX-License-Identifier: Apache-2.0
import time

from app.cdc.main import _WorkerState, build_s3_key


def test_build_s3_key_matches_layout_convention():
    key = build_s3_key(tenant_id="acme", collection_id="parcelles", dt="2026-07-17")
    assert key.startswith("cdc/tenant_id=acme/collection_id=parcelles/dt=2026-07-17/part-")
    assert key.endswith(".parquet")


def test_worker_state_tracks_last_seen_lsn():
    state = _WorkerState()
    assert state.last_seen_lsn == 0
    state.last_seen_lsn = 42
    assert state.last_seen_lsn == 42


def test_get_lag_seconds_computes_elapsed_time_since_last_flush():
    state = _WorkerState()
    state.last_flush_ts["parcelles"] = time.time() - 5
    lag = state.get_lag_seconds()
    assert 4.5 <= lag["parcelles"] <= 6.0  # marge pour l'exécution du test elle-même
