# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 2 (AUD-078/082) : bornes d'entrée des ops Python, neighborFinder borné,
troncatures signalées, géométrie des lecteurs SQL décodée."""

import duckdb
import pytest

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import execute, filtering
from app.pipelines.runtime import _decode_connector_geometry, _execute_transform_chain


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def _chain(conn, op, params, *, preview=False):
    nodes = [
        PipelineNode(id="r", kind="reader", op="reader.collection", params={"collectionId": "x"}),
        PipelineNode(id="n", kind="transform", op=op, params=params),
    ]
    edges = [PipelineEdge.model_validate({"id": "e", "from": "r", "to": "n"})]
    return _execute_transform_chain(
        conn, nodes, edges, {"r": "node_r"}, {"r": 4326}, {}, preview=preview
    )


def test_read_geometry_rows_refuses_too_many_rows(conn, monkeypatch):
    monkeypatch.setattr(execute, "MAX_GEOMETRY_ROWS", 3)
    conn.execute("CREATE TABLE src AS SELECT ST_Point(i, i) AS geometry FROM range(5) t(i)")
    with pytest.raises(PipelineRuntimeError, match="5"):
        execute._read_geometry_rows(conn, "src")


def test_read_geometry_rows_refuses_too_many_vertices(conn, monkeypatch):
    monkeypatch.setattr(execute, "MAX_GEOMETRY_VERTICES", 10)
    conn.execute(
        "CREATE TABLE src AS SELECT ST_GeomFromText("
        "'LINESTRING(0 0,1 1,2 2,3 3,4 4,5 5,6 6,7 7,8 8,9 9,10 10,11 11)') AS geometry"
    )
    with pytest.raises(PipelineRuntimeError, match="sommets"):
        execute._read_geometry_rows(conn, "src")


def test_neighbor_finder_without_distance_refuses_large_inputs(conn, monkeypatch):
    monkeypatch.setattr(filtering, "NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE", 2)
    conn.execute("CREATE TABLE a AS SELECT ST_Point(i, i) AS geometry FROM range(3) t(i)")
    with pytest.raises(PipelineRuntimeError, match="maxDistance"):
        filtering.pre_check_neighbor_finder(conn, input_view="a", params={})
    # avec maxDistance, aucun plafond
    filtering.pre_check_neighbor_finder(conn, input_view="a", params={"maxDistance": 1})


def test_neighbor_finder_pre_check_is_wired_in_the_runtime(conn, monkeypatch):
    monkeypatch.setattr(filtering, "NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE", 2)
    conn.execute("CREATE TABLE node_r AS SELECT ST_Point(i, i) AS geometry FROM range(3) t(i)")
    with pytest.raises(PipelineRuntimeError, match="maxDistance"):
        _chain(conn, "transform.neighborFinder", {})


def test_run_materializes_nodes_as_tables_preview_keeps_views(conn):
    conn.execute("CREATE TABLE node_r AS SELECT i AS v FROM range(3) t(i)")
    stats = _chain(conn, "transform.filter", {"expr": "v > 0"})
    kind = conn.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'node_n'"
    ).fetchone()[0]
    assert kind == "LOCAL TEMPORARY"
    assert stats[-1].rowCount == 2
    conn.execute("DROP TABLE node_n")
    stats = _chain(conn, "transform.filter", {"expr": "v > 0"}, preview=True)
    kind = conn.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'node_n'"
    ).fetchone()[0]
    assert kind == "VIEW"
    assert stats[-1].rowCount is None


def test_connector_geometry_is_decoded_from_wkt(conn):
    conn.execute("CREATE TEMP TABLE v AS SELECT 1 AS id, 'POINT(2 48)' AS wkt")
    srid = _decode_connector_geometry(
        conn, "v", {"geometryColumn": "wkt", "geometryFormat": "wkt", "geometrySrid": 4326}
    )
    assert srid == 4326
    cols = [d[0] for d in conn.execute("DESCRIBE v").fetchall()]
    assert cols == ["id", "geometry"]
    assert conn.execute("SELECT ST_X(geometry) FROM v").fetchone()[0] == 2


def test_connector_geometry_refuses_a_missing_column(conn):
    conn.execute("CREATE TEMP TABLE v AS SELECT 1 AS id")
    with pytest.raises(PipelineRuntimeError, match="wkt"):
        _decode_connector_geometry(conn, "v", {"geometryColumn": "wkt"})


def test_connector_without_geometry_column_is_untouched(conn):
    conn.execute("CREATE TEMP TABLE v AS SELECT 1 AS id")
    assert _decode_connector_geometry(conn, "v", {}) is None


def test_preview_evaluation_error_is_a_node_error(tmp_path, monkeypatch):
    """En aperçu les nœuds sont des VIEW non comptées : une erreur d'évaluation surgit à la
    lecture finale et doit rester une PipelineRuntimeError (400), jamais une duckdb.Error."""
    from app.configs.schemas import PipelinePayload
    from app.pipelines import runtime
    from tests.test_pipeline_runtime import _row, _table_info_for, _write_partition

    _write_partition(tmp_path, rows=[_row(1, "Nord", 10)])
    monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset())
    monkeypatch.setattr(
        runtime,
        "_table_info_for_collection",
        lambda s, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime,
        "_require_readable_collection_id",
        lambda s, *, tenant_id, user, collection_id: collection_id,
    )
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection",
             "params": {"collectionId": "villes"}},
            {"id": "t1", "kind": "transform", "op": "transform.derive",
             "params": {"column": "x", "expr": "CAST(region AS INTEGER)"}},
            {"id": "w1", "kind": "writer", "op": "writer.export",
             "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="t1"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )  # fmt: skip
