# Task 4 report — Postgres connector materialization

## What was implemented

Added `materialize_postgres_connector(conn, *, session, tenant_id, node_id, params, view_name)`
to `core/app/pipelines/connector_runtime.py`, following the brief's Step 3
almost verbatim:

1. Parses `params.query` with DuckDB's `json_serialize_sql` (via
   `app.analytics.sql_sandbox.parse_ast`) and validates it's a single
   read-only SELECT (`validate_select_only`) — same mechanism
   `app.pipelines.expr_validation` already uses for scalar expressions,
   applied here to a full SQL text instead. `SqlSandboxError` is translated
   to `ConnectorRuntimeError("reader.connector.postgres query rejected: …")`.
   This is a heuristic defense-in-depth check only (DuckDB's SQL dialect,
   not Postgres's) — never a guarantee, and only enforced at execution
   time, never at pipeline-save time (matches design §5.2/§6).
2. Resolves the `postgres_dsn` secret via the existing `_resolve_secret`
   helper; raises `ConnectorRuntimeError(...not usable by
   reader.connector.postgres...)` if the resolved secret's `kind` isn't
   `postgres_dsn`.
3. Builds a `@dlt.resource(name="records", write_disposition="replace")`
   generator that opens a SQLAlchemy engine against `payload.dsn`, runs
   `params.query` via `exec_driver_sql` with `yield_per=1000`, yields
   `dict(row._mapping)` per row, and disposes the engine in a `finally`
   block (so disposal happens even if the query raises).
4. Delegates to the existing `_run_dlt_and_attach` helper (unchanged) to
   materialize the dlt extract into a DuckDB TEMP TABLE — identical
   mechanism to Task 3's REST connector, no duplication.

Imports updated: added `import sqlalchemy as sa` and
`from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only`,
extended the `app.pipelines.ops.schemas` import to also bring in
`ReaderConnectorPostgresParams`.

## Deviations from the brief

1. **`_pg_dsn` helper bug (found and fixed).** The brief's Step 1 test code
   defines `_pg_dsn(pg_engine) -> str: return
   str(pg_engine.url).replace("postgresql+psycopg://", "postgresql://")`.
   `SQLAlchemy`'s `URL.__str__` masks the password (`gis:***@127.0.0.1:...`)
   by design — this produced a DSN with the literal password `***`, which
   fails authentication against the real Postgres container
   (`psycopg2.OperationalError: password authentication failed for user
   "gis"`), confirmed empirically on the first GREEN run attempt (13/14
   passed, only the round-trip test failed on this). Fixed by reading the
   DSN from `os.environ["CORE_TEST_DATABASE_URL"]` directly (same source
   `conftest.py::pg_engine_with_procrastinate_schema` already uses for the
   identical conversion), rather than from `str(pg_engine.url)`. Required
   adding `import os` to the test file.
2. **`_create_secret` call signature.** The brief's Step 1 code calls
   `_create_secret(session, tenant, name=..., kind=..., payload=...)`, but
   the actual helper already defined in this test file (added by Task 3)
   is `_create_secret(session, tenant, user, *, name, kind, payload)` — it
   requires a real `user` (FK `created_by` on `connector_secrets`, enforced
   under SQLite `PRAGMA foreign_keys=ON`). Adapted by adding the `user`
   fixture to `pg_secret` and to
   `test_materialize_postgres_connector_wrong_secret_kind_raises`, and
   passing it positionally, matching every other `_create_secret` call
   already in this file (e.g. `my-bearer`, `my-key`, etc.).
3. Everything else (implementation code, error messages, test bodies) was
   used verbatim from the brief — no dlt/SQLAlchemy API mismatches were
   found; `exec_driver_sql`/`execution_options(yield_per=...)` and
   `sa.create_engine` behave exactly as the brief assumed on the installed
   SQLAlchemy 2.0.51 + psycopg2 dialect.

## TDD evidence

**RED** (before implementation):
```
CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest tests/test_pipeline_connector_runtime.py -k postgres -v
```
```
FAILED tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_round_trips_query
FAILED tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_rejects_non_select
FAILED tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_wrong_secret_kind_raises
FAILED tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_missing_secret_raises
======================= 4 failed, 10 deselected in 0.78s =======================
```
All four failed with
`AttributeError: module 'app.pipelines.connector_runtime' has no attribute 'materialize_postgres_connector'`,
as expected. No skips — `pg_secret`/`pg_engine` executed against the real
container even in this RED run (confirms `CORE_TEST_DATABASE_URL` was
honored, not silently skipped).

**First GREEN attempt** (implementation done, `_pg_dsn` bug still present):
13 passed, 1 failed — `test_materialize_postgres_connector_round_trips_query`
failed with `psycopg2.OperationalError: … password authentication failed
for user "gis"` (root-caused to the `str(url)` password-masking bug above).

**GREEN** (after fixing `_pg_dsn`):
```
CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest tests/test_pipeline_connector_runtime.py -v
```
```
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_unauthenticated_no_pagination PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_extracts_records_path PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_injects_bearer_token PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_injects_api_key_query_param PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_injects_basic_auth PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_paginates_page_number PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_wrong_secret_kind_raises PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_missing_secret_raises PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_rest_connector_drops_dlt_plumbing_columns PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_round_trips_query PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_rejects_non_select PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_wrong_secret_kind_raises PASSED
tests/test_pipeline_connector_runtime.py::test_materialize_postgres_connector_missing_secret_raises PASSED
============================== 14 passed in 3.47s ==============================
```
The round-trip test actually created `sp15f_towns` in the real
`postgis-test` container, inserted 2 rows, ran the pipeline through a real
dlt→SQLAlchemy→psycopg2 connection to `127.0.0.1:5433`, and asserted the
round-tripped rows — not a skip.

**Full core suite** (regression check):
```
CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" uv run pytest -q
```
```
1233 passed, 5 skipped in 91.19s (0:01:31)
```
(the 5 skips are pre-existing `qgis`-marked tests requiring the sidecar
container, unrelated to this task — same count as before this change).

## Files changed

- `core/app/pipelines/connector_runtime.py` — added `materialize_postgres_connector`, extended imports.
- `core/tests/test_pipeline_connector_runtime.py` — added `import os`, `_pg_dsn` (fixed), `pg_secret` fixture (fixed to include `user`), and the 4 Postgres tests.

## Self-review

- SELECT-only guard rejects `DELETE FROM sp15f_towns` with
  `ConnectorRuntimeError` matching "query rejected" — confirmed by
  `test_materialize_postgres_connector_rejects_non_select` (PASSED). The
  guard runs before secret resolution and before any engine is created, so
  a rejected query never touches the network.
- Wrong secret kind (`bearer_token` used where `postgres_dsn` expected)
  raises `ConnectorRuntimeError` matching "not usable by
  reader.connector.postgres" — confirmed by
  `test_materialize_postgres_connector_wrong_secret_kind_raises` (PASSED).
- Missing secret raises `ConnectorRuntimeError` matching "not found" (via
  the existing `_resolve_secret` helper, unchanged) — confirmed by
  `test_materialize_postgres_connector_missing_secret_raises` (PASSED).
- Successful round-trip test hits the real `postgis-test` container (not
  skipped) — confirmed above, and confirmed by direct `psql`-equivalent
  SQLAlchemy connect test done before implementation
  (`sa.create_engine('postgresql://gis:gis@127.0.0.1:5433/gis_test')` →
  `SELECT 1` → `(1,)`).
- SQLAlchemy engine is disposed even if the query raises: the
  `engine.dispose()` call sits in a `finally` block wrapping the
  `with engine.connect() as db_conn: ...` block, so it runs whether
  `exec_driver_sql` succeeds, raises, or the generator is only partially
  consumed. (Rejected-query and missing/wrong-secret paths never create an
  engine at all, since those checks happen earlier — nothing to dispose in
  those cases.)
- Test output is pristine: reran the target file with `-rw` and grepped for
  "warn"/"error" in the output — no matches. Full-suite run shows a clean
  `1233 passed, 5 skipped` with no new skips or warnings introduced.

## Concerns

None blocking. One thing worth flagging for whoever reviews the whole
SP-15f branch later: the SELECT-only guard parses `params.query` with
DuckDB's SQL dialect (via `json_serialize_sql`), not Postgres's — this is
explicitly called out as a heuristic, not a guarantee, in both the design
doc (§5.2) and the code comment. A Postgres-specific SQL construct that
DuckDB's parser doesn't understand would raise `SqlSandboxError("invalid
SQL: …")` (translated to "query rejected") even for a legitimate read-only
query — a false-positive-reject failure mode, not a security hole. Nothing
to fix here (this is the design's accepted tradeoff, already documented),
just noting it's inherited unchanged from the brief.

The `_pg_dsn` bug (task 4's own test helper) is worth a note for whoever
writes Task 5+'s tests reusing the same `pg_engine`/DSN pattern: always
build DSNs with real credentials from `CORE_TEST_DATABASE_URL` directly (as
`conftest.py::pg_engine_with_procrastinate_schema` already does), never
from `str(engine.url)` — the latter is safe for logging but not for
reconnecting.
