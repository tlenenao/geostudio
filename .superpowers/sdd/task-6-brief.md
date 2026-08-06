## Task 6: Bounded SQL expression validation + DAG compiler

**Files:**
- Create: `core/app/pipelines/expr_validation.py`
- Create: `core/app/pipelines/compiler.py`
- Test: `core/tests/test_pipeline_expr_validation.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `app.analytics.sql_sandbox` (`parse_ast`, `validate_select_only`,
  `collect_table_refs`, `SqlSandboxError` — all already public names in that
  module), `PipelineNode`/`PipelineEdge` (Task 2), the 6 `Transform*Params`
  classes (Task 3).
- Produces: `validate_bounded_expr(conn, expr) -> None` (raises
  `SqlSandboxError`) in `app.pipelines.expr_validation`; `topological_order`,
  `predecessor_id`, `compile_transform_sql` in `app.pipelines.compiler` —
  consumed by Task 8's runtime.

- [ ] **Step 1: Write the failing tests for expression validation**

Create `core/tests/test_pipeline_expr_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.expr_validation import validate_bounded_expr


@pytest.fixture()
def conn():
    return duckdb.connect(":memory:")


def test_valid_scalar_expression_passes(conn):
    validate_bounded_expr(conn, "1 + 1")


def test_valid_boolean_expression_passes(conn):
    validate_bounded_expr(conn, "pop > 1000")


def test_invalid_syntax_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "pop >")


def test_expression_referencing_a_table_raises(conn):
    with pytest.raises(SqlSandboxError, match="must not reference a table"):
        validate_bounded_expr(conn, "(SELECT 1 FROM some_table)")


def test_injection_attempt_via_closing_paren_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "1) UNION SELECT password FROM users--")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_expr_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.expr_validation'`

- [ ] **Step 3: Implement `expr_validation.py`**

Create `core/app/pipelines/expr_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Validation d'une expression scalaire SQL DuckDB bornée pour
transform.filter/transform.derive/transform.aggregate.metrics (design SP-15a
§5.1 — correction de l'étude de faisabilité, qui affirmait à tort qu'un
moteur CEL tournait déjà côté serveur). Réutilise le même mécanisme AST que
app.analytics.sql_sandbox (json_serialize_sql), restreint à UNE expression
scalaire enveloppée dans un SELECT sans FROM — jamais un SELECT complet,
jamais une référence de table."""
import duckdb

from app.analytics.sql_sandbox import SqlSandboxError, collect_table_refs, parse_ast, validate_select_only


def validate_bounded_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None:
    ast = parse_ast(conn, f"SELECT ({expr})")
    validate_select_only(ast)
    if collect_table_refs(ast):
        raise SqlSandboxError("expression must not reference a table")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_expr_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 5: Write the failing tests for the compiler**

Create `core/tests/test_pipeline_compiler.py`:

```python
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
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.compiler'`

- [ ] **Step 7: Implement `compiler.py`**

Create `core/app/pipelines/compiler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Compilateur DAG→SQL du runtime étage 1 (design SP-15a §6.1). Topologie
linéaire+join uniquement (Global Constraints de ce plan — feasibility study
§4.1 D1) : chaque nœud a au plus une arête entrante, le second flux de
transform.join est un PARAM (withCollectionId), jamais une seconde arête.
Pas de fusion : compile_transform_sql produit UN fragment SQL par nœud
transform, exécuté comme sa propre TEMP VIEW par le runtime (Task 8) — ce
module ne touche jamais une connexion DuckDB, il ne fait que construire des
chaînes de caractères, testable en pur."""
from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformDeriveParams, TransformFilterParams,
    TransformJoinParams, TransformSelectParams,
)


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def topological_order(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> list[PipelineNode]:
    by_id = {n.id: n for n in nodes}
    indegree = {n.id: 0 for n in nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)
        indegree[edge.to] += 1

    queue = sorted(n.id for n in nodes if indegree[n.id] == 0)
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        newly_ready = []
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                newly_ready.append(neighbor)
        queue = sorted(queue + newly_ready)

    if len(ordered) != len(nodes):
        raise ValueError("pipeline graph must be acyclic")
    return [by_id[i] for i in ordered]


def predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    incoming = [e.from_ for e in edges if e.to == node_id]
    if len(incoming) > 1:
        raise ValueError(
            f"node '{node_id}' has more than one incoming edge "
            "(linear+join topology only, SP-15a MVP)"
        )
    return incoming[0] if incoming else None


def compile_transform_sql(
    op: str, params: dict, *, input_view: str, join_view: str | None = None,
) -> str:
    if op == "transform.filter":
        p = TransformFilterParams.model_validate(params)
        return f"SELECT * FROM {_qi(input_view)} WHERE ({p.expr})"

    if op == "transform.select":
        p = TransformSelectParams.model_validate(params)
        cols = ", ".join(
            f"{_qi(src)} AS {_qi(dst)}" if dst else _qi(src)
            for src, dst in p.columns.items()
        )
        return f"SELECT {cols} FROM {_qi(input_view)}"

    if op == "transform.derive":
        p = TransformDeriveParams.model_validate(params)
        return f"SELECT *, ({p.expr}) AS {_qi(p.column)} FROM {_qi(input_view)}"

    if op == "transform.aggregate":
        p = TransformAggregateParams.model_validate(params)
        group_cols = ", ".join(_qi(c) for c in p.groupBy)
        metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
        select_cols = ", ".join(filter(None, [group_cols, metric_cols]))
        group_clause = f" GROUP BY {group_cols}" if group_cols else ""
        return f"SELECT {select_cols} FROM {_qi(input_view)}{group_clause}"

    if op == "transform.join":
        p = TransformJoinParams.model_validate(params)
        assert join_view is not None, "transform.join requires join_view"
        join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
        return (
            f"SELECT * FROM {_qi(input_view)} {join_kw} {_qi(join_view)} "
            f"USING ({_qi(p.on)})"
        )

    raise ValueError(f"'{op}' is not a transform op")
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: PASS (11 tests green)

- [ ] **Step 9: Commit**

```bash
git add core/app/pipelines/expr_validation.py core/app/pipelines/compiler.py \
  core/tests/test_pipeline_expr_validation.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): bounded SQL expression validation + linear+join DAG compiler"
```

---

