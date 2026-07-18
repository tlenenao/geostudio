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
    assert "s3_endpoint = 'minio:9000'" in joined
    assert "s3_use_ssl = false" in joined
    assert "s3_url_style = 'path'" in joined
    assert "s3_access_key_id = 'ak'" in joined
    assert "s3_secret_access_key = 'sk'" in joined


def test_open_connection_detects_https_endpoint(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="https://minio.example.com", access_key="ak", secret_key="sk")

    assert "s3_use_ssl = true" in "\n".join(recording.statements)
