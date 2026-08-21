# SPDX-License-Identifier: Apache-2.0
import os
import threading
import time
from unittest.mock import patch

import pytest

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


def test_get_lag_seconds_thread_safe_under_concurrent_writes():
    """Réplique le race trouvé en revue : le callback de gauge OTel
    (get_lag_seconds) tourne sur un thread séparé du thread worker principal
    qui écrit dans last_flush_ts via record_flush (_flush_table). Sans le
    verrou partagé, un `dict changed size during iteration` peut être levé
    ici — non déterministe en CPython, donc ce test boucle un grand nombre
    d'itérations sur un intervalle borné pour maximiser la chance de
    déclencher la race s'il n'était pas protégé, plutôt que de dépendre d'un
    seul essai."""
    state = _WorkerState()
    stop = threading.Event()
    errors = []

    def writer():
        i = 0
        while not stop.is_set():
            state.record_flush(f"collection-{i % 50}", time.time())
            i += 1

    def reader():
        try:
            while not stop.is_set():
                state.get_lag_seconds()
        except RuntimeError as exc:  # pragma: no cover - only on regression
            errors.append(exc)

    writer_thread = threading.Thread(target=writer)
    reader_thread = threading.Thread(target=reader)
    writer_thread.start()
    reader_thread.start()
    time.sleep(0.5)
    stop.set()
    writer_thread.join(timeout=2)
    reader_thread.join(timeout=2)

    assert errors == []


def test_get_lag_seconds_respects_externally_held_lock():
    """Vérification directe (pas dépendante du timing d'une itération, qui
    serait trop rapide pour créer une fenêtre de course fiable) que
    get_lag_seconds() passe bien par state._lock : si le lock est déjà tenu
    par un autre thread, l'appel doit rester bloqué jusqu'à sa libération —
    ce qui échouerait immédiatement (get_lag_seconds retournerait tout de
    suite) si l'implémentation n'utilisait pas ce verrou."""
    state = _WorkerState()
    state.last_flush_ts["parcelles"] = time.time()
    result = {}
    done = threading.Event()

    def reader():
        result["lag"] = state.get_lag_seconds()
        done.set()

    state._lock.acquire()
    try:
        reader_thread = threading.Thread(target=reader)
        reader_thread.start()
        # Le reader ne doit pas pouvoir terminer tant que le lock est tenu.
        assert done.wait(timeout=0.2) is False
    finally:
        state._lock.release()

    reader_thread.join(timeout=2)
    assert done.is_set()
    assert "parcelles" in result["lag"]


def test_record_flush_respects_externally_held_lock():
    """Même vérification côté écriture (record_flush, appelé par
    _flush_table sur le thread worker principal)."""
    state = _WorkerState()
    done = threading.Event()

    def writer():
        state.record_flush("parcelles", time.time())
        done.set()

    state._lock.acquire()
    try:
        writer_thread = threading.Thread(target=writer)
        writer_thread.start()
        assert done.wait(timeout=0.2) is False
    finally:
        state._lock.release()

    writer_thread.join(timeout=2)
    assert done.is_set()
    assert "parcelles" in state.last_flush_ts


def test_write_and_upload_removes_temp_file_when_upload_fails(tmp_path):
    """Reproduit le leak trouvé en revue : write_geoparquet réussit (crée le
    fichier local) mais upload_parquet_file échoue (panne MinIO/réseau
    transitoire) — le fichier temporaire local doit quand même être
    supprimé, et l'exception d'origine doit continuer à se propager (le
    crash-and-restart du worker reste intentionnel, ce fix ne fait que
    fermer le leak de fichier)."""
    from app.cdc.main import _write_and_upload

    local_path = str(tmp_path / "cdc-test.parquet")

    def fake_write_geoparquet(rows, *, srid, path):
        with open(path, "wb") as fh:
            fh.write(b"fake-parquet-bytes")

    def fake_upload_that_fails(client, *, bucket, key, local_path):
        raise ConnectionError("simulated transient MinIO failure")

    with (
        patch("app.cdc.main.write_geoparquet", side_effect=fake_write_geoparquet),
        patch("app.cdc.main.storage.upload_parquet_file", side_effect=fake_upload_that_fails),
    ):
        with pytest.raises(ConnectionError):
            _write_and_upload(
                [],
                srid=4326,
                local_path=local_path,
                s3_client=None,
                bucket="b",
                key="k",
            )

    assert os.path.exists(local_path) is False


def test_write_and_upload_removes_temp_file_when_write_fails(tmp_path):
    """Même garantie côté write_geoparquet : s'il échoue avant même de créer
    le fichier (géométrie malformée), le bloc finally ne doit pas lever à
    son tour (garde `if os.path.exists`)."""
    from app.cdc.main import _write_and_upload

    local_path = str(tmp_path / "cdc-test.parquet")

    def fake_write_that_fails(rows, *, srid, path):
        raise ValueError("simulated malformed geometry")

    with patch("app.cdc.main.write_geoparquet", side_effect=fake_write_that_fails):
        with pytest.raises(ValueError):
            _write_and_upload(
                [],
                srid=4326,
                local_path=local_path,
                s3_client=None,
                bucket="b",
                key="k",
            )

    assert os.path.exists(local_path) is False


def test_write_and_upload_removes_temp_file_on_success(tmp_path):
    from app.cdc.main import _write_and_upload

    local_path = str(tmp_path / "cdc-test.parquet")

    def fake_write_geoparquet(rows, *, srid, path):
        with open(path, "wb") as fh:
            fh.write(b"fake-parquet-bytes")

    with (
        patch("app.cdc.main.write_geoparquet", side_effect=fake_write_geoparquet),
        patch("app.cdc.main.storage.upload_parquet_file") as fake_upload,
    ):
        _write_and_upload(
            [],
            srid=4326,
            local_path=local_path,
            s3_client=None,
            bucket="b",
            key="k",
        )
        fake_upload.assert_called_once()

    assert os.path.exists(local_path) is False
