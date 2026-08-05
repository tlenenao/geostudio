# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.compiler import compile_transform_sql, predecessor_id, topological_order


def _node(id_, kind, op, **params) -> PipelineNode:
    return PipelineNode(id=id_, kind=kind, op=op, params=params)


def _edge(id_, from_, to) -> PipelineEdge:
    return PipelineEdge(id=id_, **{"from": from_}, to=to)


def test_topological_order_linear_chain():
    nodes = [
        _node("w1", "writer", "writer.collection", collectionId="out"),
        _node("r1", "reader", "reader.collection", collectionId="in"),
        _node("t1", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "r1", "t1"), _edge("e2", "t1", "w1")]
    ordered_ids = [n.id for n in topological_order(nodes, edges)]
    assert ordered_ids == ["r1", "t1", "w1"]


def test_topological_order_raises_on_cycle():
    nodes = [
        _node("a", "transform", "transform.filter", expr="1=1"),
        _node("b", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "a")]
    with pytest.raises(ValueError, match="acyclic"):
        topological_order(nodes, edges)


def test_predecessor_id_returns_single_upstream():
    edges = [_edge("e1", "r1", "t1")]
    assert predecessor_id("t1", edges) == "r1"


def test_predecessor_id_returns_none_when_no_incoming_edge():
    assert predecessor_id("r1", []) is None


def test_predecessor_id_raises_on_multiple_incoming_edges():
    edges = [_edge("e1", "r1", "w1"), _edge("e2", "r2", "w1")]
    with pytest.raises(ValueError, match="one incoming edge"):
        predecessor_id("w1", edges)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE base (id INTEGER, region VARCHAR, pop INTEGER)")
    c.execute("INSERT INTO base VALUES (1, 'Nord', 10), (2, 'Sud', 5), (3, 'Nord', 20)")
    return c


def test_compile_filter(conn):
    sql = compile_transform_sql("transform.filter", {"expr": "pop > 8"}, input_view="base")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id FROM out ORDER BY id").fetchall()
    assert rows == [(1,), (3,)]


def test_compile_select_with_rename(conn):
    sql = compile_transform_sql(
        "transform.select", {"columns": {"region": "zone", "pop": None}}, input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["zone", "pop"]


def test_compile_derive(conn):
    sql = compile_transform_sql(
        "transform.derive", {"column": "pop_double", "expr": "pop * 2"}, input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn.execute("SELECT pop_double FROM out WHERE id = 1").fetchone()
    assert row == (20,)


def test_compile_aggregate(conn):
    sql = compile_transform_sql(
        "transform.aggregate",
        {"groupBy": ["region"], "metrics": {"total_pop": "SUM(pop)"}},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn.execute("SELECT region, total_pop FROM out").fetchall())
    assert rows == {"Nord": 30, "Sud": 5}


def test_compile_join(conn):
    conn.execute("CREATE TABLE other (id INTEGER, label VARCHAR)")
    conn.execute("INSERT INTO other VALUES (1, 'A'), (2, 'B')")
    sql = compile_transform_sql(
        "transform.join", {"withCollectionId": "x", "on": "id", "how": "inner"},
        input_view="base", join_view="other",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, label FROM out ORDER BY id").fetchall()
    assert rows == [(1, "A"), (2, "B")]


def test_compile_join_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql(
            "transform.join", {"withCollectionId": "x", "on": "id"}, input_view="base",
        )


def test_compile_unknown_transform_op_raises():
    with pytest.raises(ValueError, match="not a transform op"):
        compile_transform_sql("reader.collection", {"collectionId": "x"}, input_view="base")
