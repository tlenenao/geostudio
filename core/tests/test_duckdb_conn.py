# SPDX-License-Identifier: Apache-2.0
from app.analytics.duckdb_conn import open_spatial_connection


def test_open_spatial_connection_loads_the_spatial_extension():
    conn = open_spatial_connection()
    try:
        row = conn.execute("SELECT ST_AsText(ST_Point(1, 2))").fetchone()
        assert row[0] == "POINT (1 2)"
    finally:
        conn.close()


def test_open_spatial_connection_requires_no_s3_env_vars(monkeypatch):
    for var in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    conn = open_spatial_connection()
    conn.close()
