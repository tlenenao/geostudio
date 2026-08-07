### Task 3: `POST /collections/{id}/export` (aggregate mode, collection-backed)

**Files:**
- Modify: `core/app/features/routes.py`
- Test: `core/tests/test_features_export_routes.py` (new — this file also gets Task 4's tests)

**Interfaces:**
- Consumes: `rows_to_format`, `EXPORT_MEDIA_TYPES`, `export_filename` from `app.analytics.export` (Task 2); `run_collection_aggregate`, `UnknownAggregateField` (already imported in this file); `get_readable_collection`, `get_introspector` (already imported); `write_audit` (already imported).
- Produces: route `POST /collections/{collection_id}/export?format=csv|xlsx`, body `AggregateRequestBody` — used by Task 8 (shell `exportDataSource`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_features_export_routes.py`. This mirrors the fixture in `core/tests/test_features_aggregate_routes.py` exactly (same `env` fixture shape):

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="villes", pk_column="id", geometry_column="geometry",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="region", type="string", required=True),
                          ColumnInfo(name="pop", type="integer", required=True)])


def fake_introspector(session, table_name):
    if table_name != "villes":
        raise TableNotFound(table_name)
    return INFO


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-07"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(tmp_path):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (lambda session, table: None)

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: fake_duckdb_factory
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)

    client = TestClient(app)
    return app, client, admin, regular, tmp_path, tenant_id


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    return client.post("/collections", json={"tableName": "villes", "isPublic": public}).json()


def _seed(tmp_path, tenant_id, collection_id):
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=collection_id, rows=[
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)},
        {"id": 2, "region": "Sud", "pop": 5, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(1, 1)},
    ])


def test_export_aggregate_csv_returns_a_csv_attachment(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert 'attachment; filename="' in resp.headers["content-disposition"]
    assert "region,value" in resp.text or "region" in resp.text.splitlines()[0]


def test_export_aggregate_xlsx_returns_an_xlsx_attachment(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    resp = client.post(f"/collections/{col['id']}/export?format=xlsx", json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_export_aggregate_rejects_unknown_format(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    resp = client.post(f"/collections/{col['id']}/export?format=pdf", json={"groupBy": "region"})
    assert resp.status_code == 400


def test_export_aggregate_requires_authentication(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    assert resp.status_code == 401


def test_export_aggregate_denies_a_user_without_read_access(env):
    app, client, admin, regular, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=False)
    _as(app, regular)
    resp = client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    assert resp.status_code == 403


def test_export_aggregate_writes_an_audit_log_row(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    Session = app.dependency_overrides[db.get_session].__wrapped__ if False else None  # unused, kept for clarity
    with request_scoped_session(make_session_factory(make_engine("sqlite+pysqlite:///:memory:"))) as _s:
        pass  # placeholder no-op — real assertion happens via the session_factory captured below
```

That last test needs a real session handle to assert against `audit_log`. Replace it with the following (uses the same `Session` factory the fixture already built, captured via a small fixture change):

- [ ] **Step 1b: Fix the audit-log test to use a real session**

Edit the `env` fixture to also return the `Session` factory, and rewrite the audit test:

```python
@pytest.fixture()
def env(tmp_path):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (lambda session, table: None)

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: fake_duckdb_factory
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)

    client = TestClient(app)
    return app, client, admin, regular, tmp_path, tenant_id, Session
```

(Note: this adds a 7th item to the returned tuple — every other test in this file must unpack `Session` too, e.g. `app, client, admin, _r, tmp_path, tenant_id, _Session = env`. Update every test above accordingly.)

Now replace the broken audit test with:

```python
def test_export_aggregate_writes_an_audit_log_row(env):
    app, client, admin, _r, tmp_path, tenant_id, Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    client.post(f"/collections/{col['id']}/export?format=csv", json={"groupBy": "region"})
    with Session() as s:
        from app.audit.models import AuditLog
        rows = s.query(AuditLog).filter_by(action="export.run").all()
    assert len(rows) == 1
    assert rows[0].payload == {"format": "csv", "mode": "aggregate"}
    assert rows[0].object_id == col["id"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -v`
Expected: FAIL — 404 (route doesn't exist yet) on every test.

- [ ] **Step 3: Implement the route**

Edit `core/app/features/routes.py`. First, broaden the import line and the reserved-params set:

```python
from app.analytics.aggregate import AggregateRequestBody, UnknownAggregateField, run_collection_aggregate
from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format, rows_to_format
from app.analytics.sql_sandbox import SqlSandboxError, run_analyst_sql
```

Change:
```python
RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "geom_intersects", "f"}
```
to:
```python
RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "geom_intersects", "f", "format"}
```

Then add the route right after `aggregate_features` (after its closing `return {"categoryKey": category_key, "rows": rows}`):

```python
EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}


@router.post("/collections/{collection_id}/export")
def export_collection_aggregate(
    collection_id: str, body: AggregateRequestBody, format: str = Query(...),
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
):
    if format not in EXPORT_FORMATS_AGGREGATE:
        raise _validation_error(
            [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}])
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    conn = conn_factory()
    try:
        try:
            _category_key, rows = run_collection_aggregate(
                conn, base_uri=base_uri, tenant_id=col.tenant_id, collection_id=col.id,
                table_info=info, request=body,
            )
        except UnknownAggregateField as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_field", "message": exc.message}])
    finally:
        conn.close()
    content = rows_to_format(rows, format=format)
    filename = export_filename(col.title, format=format)
    write_audit(session, tenant_id=col.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="collection", object_id=col.id,
                payload={"format": format, "mode": "aggregate"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

`get_current_user` must be imported — check the top of the file: it currently imports only `get_current_user, get_current_user_optional`? Confirm with `grep -n "get_current_user" core/app/features/routes.py | head -3` — if `get_current_user` (non-optional) isn't already imported, add it to the existing `from app.auth.dependency import ...` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -v`
Expected: PASS (all tests written so far in this file — Task 4 adds more to the same file, run again at the end of Task 4)

- [ ] **Step 5: Commit**

```bash
git add core/app/features/routes.py core/tests/test_features_export_routes.py
git commit -m "feat(core): SP-16a — POST /collections/{id}/export (mode agrégé CSV/XLSX)"
```

---

