## Task 4: Postgres connector materialization — `connector_runtime.py` (part 2)

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `app.analytics.sql_sandbox.parse_ast`, `validate_select_only`,
  `SqlSandboxError` (existing, already imported the same way by
  `app.pipelines.expr_validation`).
- Produces: `app.pipelines.connector_runtime.materialize_postgres_connector(conn, *, session, tenant_id, node_id, params, view_name) -> None`.
  Consumed by Task 5 (`runtime.py`'s `_prepare()`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_connector_runtime.py`:

```python
from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams


def _pg_dsn(pg_engine) -> str:
    # Même conversion que conftest.py::pg_engine_with_procrastinate_schema :
    # CORE_TEST_DATABASE_URL est au format SQLAlchemy "postgresql+psycopg://",
    # le DSN d'un secret postgres_dsn est un DSN "postgresql://" ordinaire
    # (format vérifié par SP-15e's test_secrets_repository.py).
    return str(pg_engine.url).replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
def pg_secret(session, tenant, pg_engine):
    return _create_secret(
        session, tenant, name="warehouse-pg", kind="postgres_dsn",
        payload={"kind": "postgres_dsn", "dsn": _pg_dsn(pg_engine)},
    )


def test_materialize_postgres_connector_round_trips_query(conn, session, tenant, pg_engine, pg_secret):
    from sqlalchemy import text

    with pg_engine.begin() as db_conn:
        db_conn.execute(text("CREATE TABLE IF NOT EXISTS sp15f_towns (id int, name text)"))
        db_conn.execute(text("DELETE FROM sp15f_towns"))
        db_conn.execute(text("INSERT INTO sp15f_towns (id, name) VALUES (1, 'Nord'), (2, 'Sud')"))

    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="SELECT id, name FROM sp15f_towns ORDER BY id")
    connector_runtime.materialize_postgres_connector(
        conn, session=session, tenant_id=tenant.id, node_id="p1", params=params, view_name="node_p1",
    )
    rows = conn.execute("SELECT id, name FROM node_p1 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]


def test_materialize_postgres_connector_rejects_non_select(conn, session, tenant, pg_secret):
    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="DELETE FROM sp15f_towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p2", params=params, view_name="node_p2",
        )


def test_materialize_postgres_connector_wrong_secret_kind_raises(conn, session, tenant):
    _create_secret(session, tenant, name="bearer-secret", kind="bearer_token",
                    payload={"kind": "bearer_token", "token": "tok"})
    params = ReaderConnectorPostgresParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.postgres"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p3", params=params, view_name="node_p3",
        )


def test_materialize_postgres_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorPostgresParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p4", params=params, view_name="node_p4",
        )
```

These four tests need `pg_engine` (from `core/tests/conftest.py`) — add the
fixture to the test function signatures above (already done); no new
fixtures beyond `_pg_dsn`/`pg_secret` need to be added to `conftest.py`
itself. Tests using `pg_engine` transitively skip with
`pytest.skip("CORE_TEST_DATABASE_URL non défini...")` when no test database
is configured, same as every other `postgis`-marked test in this repo — no
new pytest marker needed (`conftest.py`'s existing `pg_engine` fixture
already handles the skip).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k postgres -v`
Expected: FAIL — `AttributeError: module 'app.pipelines.connector_runtime' has no attribute 'materialize_postgres_connector'`.

- [ ] **Step 3: Implement `materialize_postgres_connector`**

Modify `core/app/pipelines/connector_runtime.py` — add to the imports:

```python
import sqlalchemy as sa

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams, ReaderConnectorRestParams
```

(replacing the single-line `from app.pipelines.ops.schemas import ReaderConnectorRestParams` from Task 3).

Append at the end of the file:

```python
def materialize_postgres_connector(
    conn, *, session: Session, tenant_id: str, node_id: str,
    params: ReaderConnectorPostgresParams, view_name: str,
) -> None:
    # Défense en profondeur heuristique, pas une garantie (design §5.2) :
    # `params.query` cible Postgres mais est parsée avec le dialecte SQL de
    # DuckDB (même mécanisme que app.pipelines.expr_validation, appliqué ici
    # à un texte SQL complet plutôt qu'à une expression bornée). Vérifié à
    # l'exécution uniquement, jamais à la sauvegarde du pipeline.
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.postgres query rejected: {exc}") from exc

    payload = _resolve_secret(session, tenant_id, params.secretName)
    if payload.kind != "postgres_dsn":
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.postgres "
            "(expected postgres_dsn)"
        )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `CORE_TEST_DATABASE_URL=<your test db url> cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v`
Expected: all pass (REST tests from Task 3 unaffected; Postgres tests pass
if `CORE_TEST_DATABASE_URL` is set, otherwise skip cleanly — both are
acceptable outcomes, matching this repo's existing `postgis`-gated tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/connector_runtime.py core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(core): pipelines — reader.connector.postgres materialization (SELECT-only guard)"
```

---

