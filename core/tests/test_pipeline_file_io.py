# SPDX-License-Identifier: Apache-2.0
import json
import os

import duckdb
import pytest

from app.analytics.duckdb_conn import open_connection
from app.auth.dependency import is_pipeline_file_io_enabled
from app.pipelines import registries, runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog


def test_is_pipeline_file_io_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    assert is_pipeline_file_io_enabled() is False


def test_is_pipeline_file_io_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    assert is_pipeline_file_io_enabled() is True
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert is_pipeline_file_io_enabled() is False


def test_reader_file_and_writer_file_hidden_from_catalog_by_default(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    catalog = ops_catalog()
    assert "reader.file" not in catalog
    assert "writer.file" not in catalog


def test_reader_file_and_writer_file_visible_in_catalog_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    catalog = ops_catalog()
    assert catalog["reader.file"]["kind"] == "reader"
    assert catalog["writer.file"]["kind"] == "writer"


def test_operations_registry_has_reader_and_writer_file_contracts():
    assert OPERATIONS["reader.file"].kind == "reader"
    assert OPERATIONS["writer.file"].kind == "writer"


def _connection() -> duckdb.DuckDBPyConnection:
    return open_connection(endpoint_url="http://localhost:9000", access_key="x", secret_key="y")


def test_lock_down_without_extra_dirs_blocks_arbitrary_write(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    runtime._lock_down(conn)
    out_path = str(tmp_path / "out.csv")
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")


def test_lock_down_with_extra_dirs_allows_write_under_them(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    runtime._lock_down(conn, extra_allowed_dirs=[str(tmp_path)])
    out_path = str(tmp_path / "out.csv")
    conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")
    assert os.path.exists(out_path)


def test_lock_down_with_extra_dirs_still_blocks_paths_outside_them(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    runtime._lock_down(conn, extra_allowed_dirs=[str(allowed_dir)])
    out_path = str(other_dir / "out.csv")
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")


def _write_geojson(tmp_path, *, name="in.geojson"):
    path = tmp_path / name
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"label": "a"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
            {
                "type": "Feature",
                "properties": {"label": "b"},
                "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
            },
        ],
    }
    path.write_text(json.dumps(feature_collection))
    return str(path)


def test_read_file_raises_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    path = _write_geojson(tmp_path)
    conn = _connection()
    with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
        runtime._read_file(
            conn,
            session=None,
            tenant_id="t1",
            node_id="r1",
            params={"path": path},
            view_name="node_r1",
            user=None,
            base_uri="unused",
        )


def test_read_file_materializes_geojson_with_detected_srid(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson(tmp_path)
    conn = _connection()
    srid = runtime._read_file(
        conn,
        session=None,
        tenant_id="t1",
        node_id="r1",
        params={"path": path},
        view_name="node_r1",
        user=None,
        base_uri="unused",
    )
    assert srid == 4326
    rows = conn.execute("SELECT label FROM node_r1 ORDER BY label").fetchall()
    assert rows == [("a",), ("b",)]
    cols = {d[0] for d in conn.execute("SELECT * FROM node_r1 LIMIT 0").description}
    assert "geometry" in cols


def test_read_file_srid_param_overrides_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson(tmp_path)
    conn = _connection()
    srid = runtime._read_file(
        conn,
        session=None,
        tenant_id="t1",
        node_id="r1",
        params={"path": path, "srid": 2154},
        view_name="node_r1",
        user=None,
        base_uri="unused",
    )
    assert srid == 2154


def test_readers_registry_has_reader_file():
    assert registries.READERS["reader.file"] is runtime._read_file
