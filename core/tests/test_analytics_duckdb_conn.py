# SPDX-License-Identifier: Apache-2.0
"""Teste la SÉQUENCE de configuration (extensions + S3), pas la connectivité
réseau réelle (ça, c'est le spike Task 1 + le script empirique Task 10) —
via un connecteur DuckDB réel en mémoire, en interceptant .execute() pour
capturer les statements exécutés sans réseau."""

from app.analytics.duckdb_conn import open_connection


class _RecordingConnection:
    def __init__(self, real):
        self._real = real
        self.statements: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        return self._real.execute(sql, *args, **kwargs)


def test_open_connection_installs_and_loads_httpfs_and_spatial(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    assert "INSTALL httpfs" in joined and "LOAD httpfs" in joined
    assert "INSTALL spatial" in joined and "LOAD spatial" in joined


def test_open_connection_configures_s3_settings_from_endpoint(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    # REV-332 : un CREATE SECRET (illisible via current_setting), plus de SET s3_*.
    assert "CREATE OR REPLACE TEMPORARY SECRET" in joined
    assert "ENDPOINT 'minio:9000'" in joined
    assert "USE_SSL false" in joined
    assert "URL_STYLE 'path'" in joined
    assert "KEY_ID 'ak'" in joined and "SECRET 'sk'" in joined
    assert "SET s3_secret_access_key" not in joined


def test_open_connection_detects_https_endpoint(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="https://minio.example.com", access_key="ak", secret_key="sk")

    assert "USE_SSL true" in "\n".join(recording.statements)


def test_open_connection_installs_and_loads_h3(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    assert "INSTALL h3 FROM community" in joined and "LOAD h3" in joined


def test_open_local_connection_installs_and_loads_spatial_only(monkeypatch):
    import duckdb

    from app.analytics.duckdb_conn import open_local_connection

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_local_connection()

    joined = "\n".join(recording.statements)
    assert "INSTALL spatial" in joined and "LOAD spatial" in joined
    assert "httpfs" not in joined
    assert "s3_" not in joined
