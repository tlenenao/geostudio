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


def _noop_reader(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri):
    # Reader minimal sans dépendance DB, juste pour donner à _prepare() un
    # nœud reader valide (elle exige "at least one reader node" — cf.
    # PipelinePayload) sans passer par reader.collection (session réelle).
    conn.execute(f"CREATE TEMP TABLE {view_name} AS SELECT 1 AS n")
    return 4326


def test_prepare_does_not_widen_allowed_directories_when_file_io_disabled(tmp_path, monkeypatch):
    # C1 (revue finale, CRITICAL) : un nœud writer.file dans le payload ne
    # doit PAS élargir allowed_directories quand le flag est éteint — sinon
    # un transform.derive lu AVANT ce writer (ex. en preview tronquée) peut
    # lire un fichier arbitraire hors /scratch avec le flag OFF.
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    monkeypatch.setitem(registries.READERS, "reader.noop", _noop_reader)
    conn = _connection()
    payload = PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.noop",
                    "params": {},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.file",
                    "params": {"path": str(tmp_path / "out.gpkg")},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )
    runtime._prepare(conn, None, payload, tenant_id="t1", user=None, base_uri="unused")
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    leak_path = str(tmp_path / "leak.csv")
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"COPY (SELECT * FROM t) TO '{leak_path}' WITH (FORMAT CSV)")


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


def test_read_file_excludes_geopackage_fid_column(tmp_path, monkeypatch):
    # I1 (revue finale, IMPORTANT) : ST_Read() sur un GeoPackage expose
    # toujours "fid" (spec OGC GeoPackage) — sans exclusion, un writer.collection
    # en aval rejette cette propriété comme inconnue.
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    write_conn = _connection()
    write_conn.execute("INSTALL spatial; LOAD spatial;")
    write_conn.execute(
        "CREATE TEMP TABLE src AS SELECT 'a' AS label, ST_Point(1, 2) AS geometry "
        "UNION ALL SELECT 'b', ST_Point(3, 4)"
    )
    gpkg_path = tmp_path / "in.gpkg"
    write_conn.execute(
        f"COPY (SELECT * FROM src) TO '{gpkg_path}' "
        "WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:4326')"
    )
    read_conn = _connection()
    runtime._read_file(
        read_conn,
        session=None,
        tenant_id="t1",
        node_id="r1",
        params={"path": str(gpkg_path)},
        view_name="node_r1",
        user=None,
        base_uri="unused",
    )
    cols = {d[0] for d in read_conn.execute("SELECT * FROM node_r1 LIMIT 0").description}
    assert "fid" not in cols
    assert cols == {"label", "geometry"}


def _write_geojson_with_geometry_property(tmp_path):
    path = tmp_path / "collision.geojson"
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                # La clé "geometry" DANS properties (une chaîne, pas une
                # géométrie) entre en collision avec le nom que _read_file
                # veut donner à la vraie colonne géométrie.
                "properties": {"label": "a", "geometry": "not-a-geometry"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
        ],
    }
    path.write_text(json.dumps(feature_collection))
    return str(path)


def test_read_file_raises_on_geometry_name_collision(tmp_path, monkeypatch):
    # I2 (revue finale, IMPORTANT) : sans ce garde, DuckDB renomme
    # silencieusement la vraie colonne géométrie (ex. "geom") et l'alias
    # "AS geometry" écrase alors la propriété utilisateur — corruption
    # silencieuse, jamais une erreur.
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson_with_geometry_property(tmp_path)
    conn = _connection()
    with pytest.raises(PipelineRuntimeError, match="geometry"):
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


def _write_geojson_with_capitalized_geometry_property(tmp_path):
    path = tmp_path / "collision-case.geojson"
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                # "Geometry" (G majuscule) : distincte de "geometry" en Python,
                # mais DuckDB résout les identifiants sans respecter la casse —
                # le garde de collision doit donc comparer sans casse lui aussi.
                "properties": {"label": "a", "Geometry": "not-a-geometry"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
        ],
    }
    path.write_text(json.dumps(feature_collection))
    return str(path)


def test_read_file_raises_on_geometry_name_collision_case_insensitive(tmp_path, monkeypatch):
    # N1 (re-revue, IMPORTANT incomplet) : le garde de collision ajouté par
    # la revue précédente comparait "geometry" en respectant la casse. Une
    # propriété "Geometry" (G majuscule) passait donc le garde, alors que
    # DuckDB déduplique l'identifiant réel (case-insensitive) en le
    # renommant "geometry_1" — la même corruption silencieuse que le garde
    # devait empêcher, juste atteignable via une variante de casse.
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson_with_capitalized_geometry_property(tmp_path)
    conn = _connection()
    with pytest.raises(PipelineRuntimeError, match="geometry"):
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


def test_read_file_excludes_ogc_fid_column_from_geojson(tmp_path, monkeypatch):
    # N2 (re-revue, IMPORTANT incomplet) : ST_Read() sur un GeoJSON (ou un
    # Shapefile) expose un identifiant de ligne synthétique nommé "OGC_FID"
    # (pas "fid", réservé au GeoPackage) — le garde d'exclusion de _read_file
    # ne retirait que "fid" en casse exacte, donc "OGC_FID" survivait et
    # faisait échouer un writer.collection en aval, exactement le défaut que
    # I1 devait fermer pour ces formats.
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson(tmp_path)
    conn = _connection()
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
    cols = {d[0].lower() for d in conn.execute("SELECT * FROM node_r1 LIMIT 0").description}
    assert "ogc_fid" not in cols


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
