# SPDX-License-Identifier: Apache-2.0
import json
import os

import duckdb
import pytest

from app.analytics.duckdb_conn import open_connection
from app.auth.dependency import is_pipeline_file_io_enabled
from app.configs.schemas import PipelineNode, PipelinePayload
from app.pipelines import registries, runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.pipelines.runtime import NodeStat, run_pipeline


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


def _materialized_view(conn, *, view_name="node_r1"):
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute(
        f"CREATE TEMP TABLE {view_name} AS "
        "SELECT 'a' AS label, ST_Point(1, 2) AS geometry "
        "UNION ALL SELECT 'b', ST_Point(3, 4)"
    )
    return view_name


def test_write_file_raises_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    conn = _connection()
    view_name = _materialized_view(conn)
    node = PipelineNode(
        id="w1", kind="writer", op="writer.file", params={"path": str(tmp_path / "out.gpkg")}
    )
    with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
        runtime._write_file(conn, node=node, view_by_node={"w1": view_name}, srid=4326)


def test_write_file_writes_readable_gpkg(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    conn = _connection()
    view_name = _materialized_view(conn)
    out_path = tmp_path / "out.gpkg"
    node = PipelineNode(id="w1", kind="writer", op="writer.file", params={"path": str(out_path)})
    stat = runtime._write_file(conn, node=node, view_by_node={"w1": view_name}, srid=4326)
    assert isinstance(stat, NodeStat)
    assert stat.rowCount == 2
    check_conn = _connection()
    rows = check_conn.execute(f"SELECT label FROM ST_Read('{out_path}') ORDER BY label").fetchall()
    assert rows == [("a",), ("b",)]


def test_write_file_excludes_reserved_fid_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    conn = _connection()
    view_name = "node_r1"
    conn.execute(
        f"CREATE TEMP TABLE {view_name} AS "
        "SELECT 1 AS \"OGC_FID\", 'a' AS label, ST_Point(1, 2) AS geometry"
    )
    out_path = tmp_path / "out.gpkg"
    node = PipelineNode(id="w1", kind="writer", op="writer.file", params={"path": str(out_path)})
    stat = runtime._write_file(conn, node=node, view_by_node={"w1": view_name}, srid=4326)
    assert stat.rowCount == 1
    assert out_path.exists()


def test_writers_registry_has_writer_file():
    assert registries.WRITERS["writer.file"] is runtime._write_file


def test_run_pipeline_file_to_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    in_path = _write_geojson(tmp_path, name="in.geojson")
    out_path = tmp_path / "subdir" / "out.gpkg"
    payload = PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.file",
                    "params": {"path": in_path},
                },
                {
                    "id": "t1",
                    "kind": "transform",
                    "op": "transform.select",
                    # TransformSelectParams.columns : dict {source: renommage
                    # optionnel | None}, PAS une liste — vérifié dans
                    # app/pipelines/compiler.py::_compile_select avant
                    # d'écrire ce test.
                    "params": {"columns": {"label": None, "geometry": None}},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.file",
                    "params": {"path": str(out_path)},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "w1"},
            ],
        }
    )
    stats = run_pipeline(
        session=None,
        payload=payload,
        tenant_id="t1",
        user=None,
        endpoint_url="http://localhost:9000",
        access_key="x",
        secret_key="y",
        base_uri=str(tmp_path),
    )
    assert {s.op for s in stats} == {"reader.file", "transform.select", "writer.file"}
    check_conn = _connection()
    rows = check_conn.execute(f"SELECT label FROM ST_Read('{out_path}') ORDER BY label").fetchall()
    assert rows == [("a",), ("b",)]
