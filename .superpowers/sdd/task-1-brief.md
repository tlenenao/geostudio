### Task 1: `app/configs/alert_condition.py` — bounded scalar condition expression

**Files:**
- Create: `core/app/configs/alert_condition.py`
- Test: `core/tests/test_alert_condition.py`

**Interfaces:**
- Consumes: `app.analytics.sql_sandbox.{parse_ast, validate_select_only, collect_table_refs, SqlSandboxError}` (existing, layer-free).
- Produces: `validate_condition_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None` (raises `SqlSandboxError` on an invalid/unbounded expression) and `evaluate_condition(conn: duckdb.DuckDBPyConnection, expr: str, value: float) -> bool`, both consumed by Task 2 (schema validator) and Task 9 (`app.alerts.jobs`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_condition.py
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.alerts_test_helpers import NOTHING  # placeholder import removed in step 3 — see note below
```

Replace that draft with the real test file (no placeholder import — written directly):

```python
# core/tests/test_alert_condition.py
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.configs.alert_condition import evaluate_condition, validate_condition_expr


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_validate_condition_expr_accepts_a_bounded_comparison(conn):
    validate_condition_expr(conn, "value > 100")  # must not raise


def test_validate_condition_expr_rejects_a_table_reference(conn):
    with pytest.raises(SqlSandboxError):
        validate_condition_expr(conn, "(SELECT count(*) FROM some_table)")


def test_validate_condition_expr_rejects_invalid_sql(conn):
    with pytest.raises(SqlSandboxError):
        validate_condition_expr(conn, "value >")


def test_evaluate_condition_returns_true_when_condition_holds(conn):
    assert evaluate_condition(conn, "value > 100", 150.0) is True


def test_evaluate_condition_returns_false_when_condition_does_not_hold(conn):
    assert evaluate_condition(conn, "value > 100", 50.0) is False


def test_evaluate_condition_supports_compound_expressions(conn):
    assert evaluate_condition(conn, "value >= 10 AND value <= 20", 15.0) is True
    assert evaluate_condition(conn, "value >= 10 AND value <= 20", 25.0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_condition.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.configs.alert_condition'`

- [ ] **Step 3: Write the implementation**

```python
# core/app/configs/alert_condition.py
# SPDX-License-Identifier: Apache-2.0
"""Bounded scalar SQL condition expression for kind="alert" (design SP-16b
§4). Lives in app.configs, not app.alerts, deliberately: app.alerts sits
ABOVE app.secrets in the import-linter layer contract (Global Constraints),
so if this lived in app.alerts, app.configs (a lower layer, needed for the
save-time Pydantic validator in schemas.py) could not import it back. The
function has no alert-specific knowledge — it is a generic "one bounded
scalar SQL expression, no table references" helper, same restriction as
app.pipelines.expr_validation.validate_bounded_expr but placed where both
the save-time validator (app.configs) and the run-time evaluator
(app.alerts, Task 9) can import it downward without crossing the contract.
"""
import duckdb

from app.analytics.sql_sandbox import collect_table_refs, parse_ast, validate_select_only, SqlSandboxError


def validate_condition_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None:
    ast = parse_ast(conn, f"SELECT ({expr})")
    validate_select_only(ast)
    if collect_table_refs(ast):
        raise SqlSandboxError("condition expression must not reference a table")


def evaluate_condition(conn: duckdb.DuckDBPyConnection, expr: str, value: float) -> bool:
    # `value` is bound as a real column of a derived table rather than
    # string-substituted into expr — avoids any risk of a naive text
    # replace corrupting the expression (e.g. "value" appearing inside a
    # string literal), and lets DuckDB's own SQL scoping resolve the bare
    # identifier normally.
    validate_condition_expr(conn, expr)
    row = conn.execute(f"SELECT ({expr}) FROM (SELECT ? AS value) t", [value]).fetchone()
    return bool(row[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_condition.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/alert_condition.py core/tests/test_alert_condition.py
git commit -m "feat(core): SP-16b — bounded scalar condition expression (app.configs.alert_condition)"
```

---

