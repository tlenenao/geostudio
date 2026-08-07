# SP-16a — Export serveur CSV/XLSX/GeoJSON/GPKG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user download a dataset's data as CSV, XLSX, GeoJSON, or GPKG from the core API, wired into the shell's widget "⋮" menu and `DatasetEditPage`.

**Architecture:** Two independent query modes, mirroring the existing `/aggregate` vs `/items` split (`aggregate` never carries geometry, `items` always does): a **CSV/XLSX-only** aggregate-export route (reuses `run_collection_aggregate`/`live_query.translate_aggregate_query`) and a **CSV/XLSX/GeoJSON/GPKG** raw-entities-export route (reuses `select_features`/`live_query.translate_features_query`, paginated up to a 10,000-row cap). Each mode exists once for collection-backed datasets (`app.features`) and once for arcgis-backed datasets (`app.harvest`) — four routes total, no unifying dispatcher (the import-linter layer contract forbids `app.features` from importing `app.harvest`). Serialization lives in one new shared module, `app.analytics.export`, called by all four routes. On the shell, one new `ItemClient.exportDataSource()` method mirrors the existing `queryDataSource()` dispatch; the download entry points are the existing `ExplorerMenu` (used by all 6 analytical widgets) and a new section on `DatasetEditPage`.

**Tech Stack:** FastAPI, DuckDB (`spatial` extension, already loaded elsewhere), `openpyxl` (new dependency), React/TanStack Query, Playwright.

## Global Constraints

- Export routes require authentication (`get_current_user`, never `get_current_user_optional`) — every successful export writes an `audit_log` row and needs a real `actor_id`.
- Raw-entities export (GeoJSON/GPKG/CSV/XLSX-from-items) is capped at **10,000 entities**; beyond that, respond `413` rather than truncating silently.
- No new capability flag (unlike `CORE_ETL_ENABLED`) — export is a base feature, always on, same as `/aggregate`/`items`.
- GPKG is the only format that touches disk (DuckDB `COPY ... TO` requires a filesystem path); it uses its own `tempfile.TemporaryDirectory()`, independent of the `/scratch` volume SP-15d uses for the QGIS sidecar.
- Reuse existing permission checks verbatim — no new authorization logic. Collection routes reuse `get_readable_collection`; arcgis routes reuse `_resolve_arcgis_dataset`.
- Spec: `docs/superpowers/specs/2026-08-07-sp16a-export-serveur-design.md` (read it first — this plan implements it section by section).

---

### Task 1: `openpyxl` dependency + spatial-only DuckDB connection helper

**Files:**
- Modify: `core/pyproject.toml` (dependencies list, alongside the other SP-annotated entries around line 16-26)
- Modify: `core/app/analytics/duckdb_conn.py`
- Test: `core/tests/test_duckdb_conn.py` (new)

**Interfaces:**
- Produces: `open_spatial_connection() -> duckdb.DuckDBPyConnection` in `app.analytics.duckdb_conn` — used by Task 4/6 for GPKG conversion. No S3/httpfs/h3 setup, no env vars required (GPKG conversion never touches S3), so it's trivially testable and overridable.

- [ ] **Step 1: Add the dependency**

Edit `core/pyproject.toml`, in the `dependencies = [` list (find it via `grep -n '"duckdb' core/pyproject.toml`), add a new line right after the `duckdb` entry:

```toml
    "openpyxl>=3.1",  # SP-16a : sérialisation d'export XLSX (app/analytics/export.py) —
                      # aucune dépendance XLSX n'existait dans le cœur avant ce sous-plan.
```

- [ ] **Step 2: Write the failing test for `open_spatial_connection`**

Create `core/tests/test_duckdb_conn.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.analytics.duckdb_conn import open_spatial_connection


def test_open_spatial_connection_loads_the_spatial_extension():
    conn = open_spatial_connection()
    try:
        row = conn.execute("SELECT ST_AsText(ST_Point(1, 2))").fetchone()
        assert row[0] == "POINT (1 2)"
    finally:
        conn.close()


def test_open_spatial_connection_requires_no_s3_env_vars(monkeypatch):
    for var in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    conn = open_spatial_connection()
    conn.close()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd core && uv run pytest tests/test_duckdb_conn.py -v`
Expected: FAIL — `ImportError: cannot import name 'open_spatial_connection'`

- [ ] **Step 4: Install the dependency and implement**

Run: `cd core && uv sync`

Edit `core/app/analytics/duckdb_conn.py`, add after `open_connection`:

```python
def open_spatial_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour la seule conversion GPKG des exports
    (SP-16a) : contrairement à open_connection, ne touche jamais S3 — aucune
    variable d'environnement requise, aucun httpfs/h3 chargé."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_duckdb_conn.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/app/analytics/duckdb_conn.py core/tests/test_duckdb_conn.py
git commit -m "feat(core): SP-16a — dépendance openpyxl + connexion DuckDB spatiale sans S3"
```

---

### Task 2: Serialization module `app.analytics.export`

**Files:**
- Create: `core/app/analytics/export.py`
- Test: `core/tests/test_analytics_export.py`

**Interfaces:**
- Consumes: `open_spatial_connection()` from Task 1 (test-only, for the GPKG round-trip test).
- Produces (used by Tasks 3-6):
  - `EXPORT_MEDIA_TYPES: dict[str, str]` — keys `"csv"`, `"xlsx"`, `"geojson"`, `"gpkg"`.
  - `export_filename(title: str, *, format: str) -> str`
  - `rows_to_format(rows: list[dict], *, format: str) -> bytes` — `format` must be `"csv"` or `"xlsx"`.
  - `features_to_format(features: list[dict], *, format: str, conn=None) -> bytes` — `format` one of `"csv"`/`"xlsx"`/`"geojson"`/`"gpkg"`; `conn` (a `duckdb.DuckDBPyConnection` with `spatial` loaded) is required only when `format == "gpkg"`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_analytics_export.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import json

import openpyxl
import pytest

from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    features_to_format,
    rows_to_format,
)


def test_rows_to_format_csv_has_header_and_data_rows():
    content = rows_to_format([{"region": "Nord", "pop": 10}, {"region": "Sud", "pop": 5}], format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "region,pop"
    assert "Nord,10" in text


def test_rows_to_format_csv_empty_rows_is_empty_bytes():
    assert rows_to_format([], format="csv") == b""


def test_rows_to_format_xlsx_round_trips_through_openpyxl():
    content = rows_to_format([{"region": "Nord", "pop": 10}], format="xlsx")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows == [("region", "pop"), ("Nord", 10)]


def test_rows_to_format_rejects_geojson():
    with pytest.raises(ValueError):
        rows_to_format([{"a": 1}], format="geojson")


def test_features_to_format_geojson_wraps_a_feature_collection():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="geojson")
    body = json.loads(content)
    assert body == {"type": "FeatureCollection", "features": features}


def test_features_to_format_csv_flattens_properties_and_drops_geometry():
    features = [{"type": "Feature", "properties": {"nom": "X", "pop": 3}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "nom,pop"
    assert "geometry" not in text


def test_features_to_format_gpkg_requires_a_connection():
    with pytest.raises(AssertionError):
        features_to_format([{"type": "Feature", "properties": {}, "geometry": None}], format="gpkg")


def test_features_to_format_gpkg_round_trips_a_point():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}]
    conn = open_spatial_connection()
    try:
        content = features_to_format(features, format="gpkg", conn=conn)
        assert content[:16] == b"SQLite format 3\x00"
        read_back = open_spatial_connection()
        try:
            with open("/tmp/sp16a_test.gpkg", "wb") as f:
                f.write(content)
            row = read_back.execute("SELECT nom FROM ST_Read('/tmp/sp16a_test.gpkg')").fetchone()
            assert row[0] == "X"
        finally:
            read_back.close()
    finally:
        conn.close()


def test_export_filename_slugifies_the_title_and_appends_the_format():
    name = export_filename("Bâtiments (2026)", format="csv")
    assert name.startswith("batiments-2026")
    assert name.endswith(".csv")


def test_export_filename_falls_back_to_export_for_an_empty_title():
    assert export_filename("", format="xlsx").startswith("export")


def test_export_media_types_cover_all_four_formats():
    assert set(EXPORT_MEDIA_TYPES) == {"csv", "xlsx", "geojson", "gpkg"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analytics.export'`

- [ ] **Step 3: Implement**

Create `core/app/analytics/export.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Sérialisation d'export (SP-16a) : lignes attributaires (mode agrégé,
sans géométrie par construction) ou features GeoJSON (mode entités brutes)
vers CSV/XLSX/GeoJSON/GPKG. Fonctions pures, réutilisables telles quelles
par SP-16b (rapports planifiés) sans passer par un appel HTTP interne."""
import json
import re
import tempfile
import unicodedata
from csv import DictWriter
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import Workbook

EXPORT_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "geojson": "application/geo+json",
    "gpkg": "application/geopackage+sqlite3",
}


def export_filename(title: str, *, format: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower() or "export"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{stamp}.{format}"


def rows_to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = StringIO()
    writer = DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def rows_to_xlsx(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rows_to_format(rows: list[dict], *, format: str) -> bytes:
    if format == "csv":
        return rows_to_csv(rows)
    if format == "xlsx":
        return rows_to_xlsx(rows)
    raise ValueError(f"unsupported row format '{format}'")


def features_to_geojson(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def features_to_gpkg(features: list[dict], conn) -> bytes:
    with tempfile.TemporaryDirectory() as scratch_dir:
        in_path = Path(scratch_dir) / "in.geojson"
        out_path = Path(scratch_dir) / "out.gpkg"
        in_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
        conn.execute(f"CREATE TABLE t AS SELECT * FROM ST_Read('{in_path}')")
        conn.execute(f"COPY t TO '{out_path}' WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:4326')")
        return out_path.read_bytes()


def features_to_format(features: list[dict], *, format: str, conn=None) -> bytes:
    if format in ("csv", "xlsx"):
        return rows_to_format([f.get("properties") or {} for f in features], format=format)
    if format == "geojson":
        return features_to_geojson(features)
    if format == "gpkg":
        assert conn is not None, "features_to_format(format='gpkg') requires a duckdb connection"
        return features_to_gpkg(features, conn)
    raise ValueError(f"unsupported feature format '{format}'")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_export.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/export.py core/tests/test_analytics_export.py
git commit -m "feat(core): SP-16a — module de sérialisation d'export CSV/XLSX/GeoJSON/GPKG"
```

---

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

### Task 4: `GET /collections/{id}/export/items` (raw-entities mode, collection-backed)

**Files:**
- Modify: `core/app/features/routes.py`
- Modify: `core/tests/test_features_export_routes.py` (same file as Task 3, append)

**Interfaces:**
- Consumes: `features_to_format` (Task 2), `open_spatial_connection` (Task 1), `_parse_bbox`, `_parse_geom_intersects`, `_collect_filters`, `get_features_repo`, `get_rls_scope`, `FilterError` (all already present in this file), `MAX_LIMIT` (already present, = 1000).
- Produces: route `GET /collections/{collection_id}/export/items?format=csv|xlsx|geojson|gpkg` — used by Task 8 and by Task 12 (`DatasetEditPage`, unfiltered, all formats).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_features_export_routes.py`:

```python
def test_export_items_geojson_returns_a_feature_collection(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    # items export reads from the live PostGIS-backed collection table via
    # select_features, not the GeoParquet CDC lake used by aggregate — but
    # this fixture never wrote actual rows to the fake sqlite-backed
    # collection table, only to the CDC parquet lake (_seed). To exercise
    # the items path meaningfully, create features through the normal write
    # route first.
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=geojson")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/geo+json"
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["region"] == "Nord"


def test_export_items_csv_flattens_properties(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 200
    assert "Nord" in resp.text
    assert "geometry" not in resp.text.splitlines()[0]


def test_export_items_gpkg_returns_a_sqlite_container(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_rejects_unknown_format(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    resp = client.get(f"/collections/{col['id']}/export/items?format=pdf")
    assert resp.status_code == 400


def test_export_items_caps_at_10000_entities(env, monkeypatch):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    import app.features.routes as routes_module
    monkeypatch.setattr(routes_module, "EXPORT_ITEMS_CAP", 1)
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord"}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Sud"}, "geometry": {"type": "Point", "coordinates": [1, 1]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 413
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -k items -v`
Expected: FAIL — 404 on every new test.

- [ ] **Step 3: Implement the route**

Add to `core/app/features/routes.py`, after the new `export_collection_aggregate` route:

```python
EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}
EXPORT_ITEMS_CAP = 10_000


@router.get("/collections/{collection_id}/export/items")
def export_collection_items(
    collection_id: str, request: Request, format: str = Query(...),
    bbox: str | None = None, geom_intersects: str | None = None,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    if format not in EXPORT_FORMATS_ITEMS:
        raise _validation_error(
            [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}])
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    parsed_bbox = _parse_bbox(bbox)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)

    features: list[dict] = []
    offset = 0
    while True:
        try:
            with rls(session, col.tenant_id):
                page = repo.select_features(session, info, limit=MAX_LIMIT, offset=offset,
                                            bbox=parsed_bbox, geom_intersects=parsed_geom_intersects,
                                            filters=filters or None)
        except FilterError as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
        features.extend(page.features)
        if len(features) > EXPORT_ITEMS_CAP:
            raise HTTPException(status_code=413, detail="too many entities matched, refine your filters")
        if page.number_returned < MAX_LIMIT:
            break
        offset += MAX_LIMIT

    if format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=format)
    filename = export_filename(col.title, format=format)
    write_audit(session, tenant_id=col.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="collection", object_id=col.id,
                payload={"format": format, "mode": "items"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

Add `open_spatial_connection` to the `app.analytics.duckdb_conn` import (new line, since `duckdb_conn` isn't currently imported in this file):

```python
from app.analytics.duckdb_conn import open_spatial_connection
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -v`
Expected: PASS (all tests in the file, both Task 3 and Task 4)

- [ ] **Step 5: Commit**

```bash
git add core/app/features/routes.py core/tests/test_features_export_routes.py
git commit -m "feat(core): SP-16a — GET /collections/{id}/export/items (entités brutes, 4 formats)"
```

---

### Task 5: `POST /datasets/{id}/arcgis/export` (aggregate mode, arcgis-backed)

**Files:**
- Modify: `core/app/harvest/routes.py`
- Test: `core/tests/test_harvest_dataset_arcgis_export_routes.py` (new)

**Interfaces:**
- Consumes: `rows_to_format`, `EXPORT_MEDIA_TYPES`, `export_filename` (Task 2); `_resolve_arcgis_dataset`, `_groupby_fields`, `_measure_label`, `live_query` (all already present in this file).
- Produces: route `POST /datasets/{item_id}/arcgis/export?format=csv|xlsx`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_harvest_dataset_arcgis_export_routes.py`, mirroring `core/tests/test_harvest_dataset_arcgis_routes.py`'s fixture:

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import live_query, routes as harvest_routes
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


@pytest.fixture(autouse=True)
def _clear_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="a@example.com", first_name="Alice", last_name="Doe",
        )
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=alice.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=alice.id, resource_type="external", title="Bâtiments",
        )
        harvest_repo.create_record(
            s, tenant_id=tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url=SERVICE, layer_kind="feature",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.layer_item_id = layer_item.id  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_dataset(client, arcgis_item_id: str) -> str:
    res = client.post("/configs", json={
        "title": "Bâtiments (live)",
        "config": {
            "version": 1, "kind": "dataset",
            "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
        },
    })
    assert res.status_code == 201, res.text
    return res.json()["itemId"]


def test_export_aggregate_csv_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "features": [{"attributes": {"region": "Nord", "m0": 3}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv",
                        json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Nord" in resp.text


def test_export_aggregate_rejects_unknown_format(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=pdf", json={"groupBy": "region"})
    assert resp.status_code == 400


def test_export_aggregate_writes_an_audit_log_row(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [{"attributes": {"region": "Nord", "m0": 3}}]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv", json={"groupBy": "region", "agg": "count"})
    with client.session_factory() as s:
        rows = s.query(AuditLog).filter_by(action="export.run").all()
    assert len(rows) == 1
    assert rows[0].payload == {"format": "csv", "mode": "aggregate"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: FAIL — 404 on every test.

- [ ] **Step 3: Implement**

Edit `core/app/harvest/routes.py`. Add `Response` to the fastapi import and add the export imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
```

```python
from app.analytics.aggregate import AggregateMeasure, AggregateRequestBody
from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format, rows_to_format
```

Add the route after `get_dataset_arcgis_aggregate`'s closing `return {"categoryKey": category_key, "rows": rows}`:

```python
_EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}


@router.post("/datasets/{item_id}/arcgis/export")
def export_dataset_arcgis_aggregate(
    item_id: str, body: AggregateRequestBody, format: str = Query(...),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if format not in _EXPORT_FORMATS_AGGREGATE:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}]},
        )
    if body.bucket is not None or body.split is not None or body.bins is not None:
        raise HTTPException(
            status_code=400,
            detail="bucket/split/bins are not supported for arcgis-sourced datasets",
        )
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    group_by = _groupby_fields(body.groupBy)
    measures_in = body.measures or [AggregateMeasure(field=body.field, agg=body.agg, label="value")]
    measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
    try:
        params = live_query.translate_aggregate_query(
            group_by=group_by, measures=measures, filters=body.filters, bbox=body.bbox,
        )
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_aggregate", "message": exc.message}]},
        )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    _category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
    content = rows_to_format(rows, format=format)
    item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    filename = export_filename(item.title if item else item_id, format=format)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="item", object_id=item_id,
                payload={"format": format, "mode": "aggregate"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/routes.py core/tests/test_harvest_dataset_arcgis_export_routes.py
git commit -m "feat(core): SP-16a — POST /datasets/{id}/arcgis/export (mode agrégé CSV/XLSX)"
```

---

### Task 6: `GET /datasets/{id}/arcgis/export/items` (raw-entities mode, arcgis-backed)

**Files:**
- Modify: `core/app/harvest/routes.py`
- Modify: `core/tests/test_harvest_dataset_arcgis_export_routes.py` (append)

**Interfaces:**
- Consumes: `features_to_format` (Task 2), `open_spatial_connection` (Task 1), `translate_features_query`, `fetch_query`, `_parse_bbox`, `_resolve_arcgis_dataset` (already present).
- Produces: route `GET /datasets/{item_id}/arcgis/export/items?format=csv|xlsx|geojson|gpkg`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_harvest_dataset_arcgis_export_routes.py`:

```python
def test_export_items_geojson_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    body = resp.json()
    assert body["features"][0]["properties"]["nom"] == "X"


def test_export_items_gpkg_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"},
                          "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_stops_paginating_on_a_short_page(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    assert len(calls) == 1  # one page returned fewer rows than the page size — loop stops


def test_export_items_caps_at_10000_entities(client, monkeypatch):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    monkeypatch.setattr(harvest_routes, "_EXPORT_ITEMS_CAP", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        # Always return a full page (limit=1000) so the loop keeps paginating
        # until the (monkeypatched) cap trips.
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}] * 1000,
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 413
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -k items -v`
Expected: FAIL — 404 on every new test.

- [ ] **Step 3: Implement**

Add to `core/app/harvest/routes.py`, after `export_dataset_arcgis_aggregate`, and add `open_spatial_connection` to the analytics import block:

```python
from app.analytics.duckdb_conn import open_spatial_connection
```

```python
_EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}
_EXPORT_ITEMS_CAP = 10_000


@router.get("/datasets/{item_id}/arcgis/export/items")
def export_dataset_arcgis_items(
    item_id: str, request: Request, format: str = Query(...), bbox: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if format not in _EXPORT_FORMATS_ITEMS:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}]},
        )
    parsed_bbox = _parse_bbox(bbox)
    reserved = {"limit", "offset", "bbox", "format"}
    filters = {k: v for k, v in request.query_params.items() if k not in reserved}
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)

    features: list[dict] = []
    offset = 0
    limit = _MAX_LIMIT
    try:
        while True:
            params = live_query.translate_features_query(filters=filters, bbox=parsed_bbox, limit=limit, offset=offset)
            raw = live_query.fetch_query(client, external_url, params)
            page_features = raw.get("features", []) if isinstance(raw, dict) else []
            features.extend(page_features)
            if len(features) > _EXPORT_ITEMS_CAP:
                raise HTTPException(status_code=413, detail="too many entities matched, refine your filters")
            if len(page_features) < limit:
                break
            offset += limit
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_filter", "message": exc.message}]},
        )
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()

    if format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=format)
    item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    filename = export_filename(item.title if item else item_id, format=format)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="item", object_id=item_id,
                payload={"format": format, "mode": "items"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: PASS (all tests in the file, both Task 5 and Task 6)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/routes.py core/tests/test_harvest_dataset_arcgis_export_routes.py
git commit -m "feat(core): SP-16a — GET /datasets/{id}/arcgis/export/items (entités brutes, 4 formats)"
```

---

### Task 7: Read-only demo guard — exempt export routes

**Files:**
- Modify: `core/app/main.py`
- Modify: `core/tests/test_read_only_mode.py` (append)

**Interfaces:**
- Consumes: nothing new (pure regex addition to the existing middleware).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_read_only_mode.py`:

```python
def test_read_only_mode_does_not_block_export_endpoints(env, monkeypatch):
    """POST .../export (mode agrégé) est une lecture malgré son verbe HTTP,
    même raisonnement que POST /collections/{id}/aggregate (SP-16a) : sans
    cette exemption, une démo publique en lecture seule casserait le bouton
    Exporter de tout widget analytique."""
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    resp = env.post("/collections/does-not-exist/export?format=csv", json={"groupBy": "x"})
    assert resp.status_code == 404  # jamais 403 : passé le garde, arrêté par get_readable_collection

    resp = env.post("/datasets/does-not-exist/arcgis/export?format=csv", json={"groupBy": "x"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_read_only_mode.py -k export -v`
Expected: FAIL — both requests return 403 with `{"detail": "Mode démo : lecture seule, écritures désactivées."}`.

- [ ] **Step 3: Implement**

Edit `core/app/main.py`. Change:

```python
_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")
```

to:

```python
_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")
_EXPORT_PATH_RE = re.compile(r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$")
```

Change the guard condition:

```python
    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and request.url.path != "/analytics/sql"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
            and not _EXPORT_PATH_RE.match(request.url.path)
        ):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_read_only_mode.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the full core test suite**

Run: `cd core && uv run pytest -q`
Expected: all tests pass (previously: 606 executed + 87 skipped, now +~30 new tests from Tasks 1-7)

- [ ] **Step 6: Commit**

```bash
git add core/app/main.py core/tests/test_read_only_mode.py
git commit -m "fix(core): SP-16a — exempte les routes d'export du garde lecture-seule démo"
```

---

### Task 8: Shell — `ItemClient.exportDataSource()`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Consumes: `DataSource`, `resolveDataset` (internal to `itemClient.ts`), `_queryParams`, `buildAggregateBody` (all already present).
- Produces: `ItemClient.exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }>` — used by Task 10 (`ExplorerMenu`) and Task 12 (`DatasetEditPage`).

- [ ] **Step 1: Add the type declarations**

Edit `shell/src/api/types.ts`. In the `ItemClient` interface, right after the existing line:

```ts
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
```

add:

```ts
  exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }>;
```

And in `DataSourceState`, add two optional fields:

```ts
export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
  datasetId?: string;
  pkColumn?: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
};
```

- [ ] **Step 2: Write the failing test**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("exportDataSource posts the aggregate body and extracts the filename for a statistics source", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/collections/parcs/export", async ({ request }) => {
      posted = await request.json();
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("csv");
      return new HttpResponse("region,count\nNord,3\n", {
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="parcs-20260807-120000.csv"',
        },
      });
    }),
  );
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: { groupBy: "region", agg: "count" } };
  const { blob, filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("parcs-20260807-120000.csv");
  expect(await blob.text()).toBe("region,count\nNord,3\n");
  expect(posted).toEqual({ groupBy: "region", agg: "count" });
});

test("exportDataSource GETs the items-export route for a non-statistics source", async () => {
  server.use(
    http.get("https://core.test/collections/parcs/export/items", ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("geojson");
      return new HttpResponse('{"type":"FeatureCollection","features":[]}', {
        headers: { "Content-Type": "application/geo+json", "Content-Disposition": 'attachment; filename="parcs.geojson"' },
      });
    }),
  );
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("parcs.geojson");
});

test("exportDataSource dispatches to the arcgis export route for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds1", () =>
      HttpResponse.json({ config: { dataset: { source: "arcgis", arcgisItemId: "ext1", columns: {} } } }),
    ),
    http.post("https://core.test/datasets/ds1/arcgis/export", () =>
      new HttpResponse("a,b\n1,2\n", {
        headers: { "Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="x.csv"' },
      }),
    ),
  );
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "", datasetId: "ds1", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("x.csv");
});

test("exportDataSource falls back to a generic filename when Content-Disposition is missing", async () => {
  server.use(
    http.get("https://core.test/collections/parcs/export/items", () =>
      new HttpResponse("[]", { headers: { "Content-Type": "application/geo+json" } }),
    ),
  );
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("export");
});
```

Check the top of `shell/src/api/itemClient.test.ts` imports `HttpResponse`/`http` from `msw` and `server` from `../test/msw/server` (same as Step 1's existing tests) — add `import type { DataSource } from "./types";` if not already imported.

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `TypeError: makeClient(...).exportDataSource is not a function`

- [ ] **Step 4: Implement**

Edit `shell/src/api/itemClient.ts`. Add a module-level helper right after `requestFeatureWrite` (or near `request`):

```ts
async function requestBlob(
  coreUrl: string, getToken: () => string | undefined, method: string, path: string, body?: unknown,
): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${coreUrl}${path}`, {
    method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${method} ${path}`);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match ? match[1] : "export";
  const blob = await res.blob();
  return { blob, filename };
}
```

Then, inside `createItemClient(...)`, add the method right after `queryDataSource` (which ends around line 820, before `getCollectionSchema`):

```ts
    async exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      const isArcgis = cachedDataset?.source === "arcgis" && Boolean(source.datasetId);
      if (source.type === "statistics") {
        const body = buildAggregateBody(source.query);
        const path = isArcgis
          ? `/datasets/${source.datasetId}/arcgis/export?format=${format}`
          : `/collections/${cachedDataset?.collectionId ?? source.layer}/export?format=${format}`;
        return requestBlob(coreUrl, getToken, "POST", path, body);
      }
      const resolved = source.datasetId ? { ...source, layer: cachedDataset?.collectionId ?? source.layer } : source;
      const qs = _queryParams(resolved.query);
      const suffix = qs ? `&${qs}` : "";
      const path = isArcgis
        ? `/datasets/${source.datasetId}/arcgis/export/items?format=${format}${suffix}`
        : `/collections/${resolved.layer}/export/items?format=${format}${suffix}`;
      return requestBlob(coreUrl, getToken, "GET", path);
    },
```

Check `_queryParams` is accessible at this point in the file (it's a module-level function used by `buildFeaturesUrl` at line ~166) — confirm with `grep -n "_queryParams" shell/src/api/itemClient.ts` and use its exact name.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Run the shell type check**

Run: `cd shell && npm run build`
Expected: no TypeScript errors (this exercises every other file implementing `ItemClient` — search for other implementations with `grep -rn "ItemClient {" shell/src --include=*.ts` and add a stub `exportDataSource` there too if any test double implements the full interface structurally rather than via `as unknown as ItemClient`)

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): SP-16a — ItemClient.exportDataSource() (dispatch collection/arcgis, agrégé/items)"
```

---

### Task 9: Shell — `DataContext` exposes `resolvedSource`/`hasGeometry`

**Files:**
- Modify: `shell/src/builder/DataContext.tsx`
- Modify: `shell/src/builder/DataContext.test.tsx` (append)

**Interfaces:**
- Consumes: `CollectionSchema.geometry` (already returned by `client.getCollectionSchema`), `DatasetConfig.source` (already resolved).
- Produces: `DataSourceState.resolvedSource`/`.hasGeometry` populated for every source — used by Task 10 (`ExplorerMenu`).

- [ ] **Step 1: Write the failing test**

Read `shell/src/builder/DataContext.test.tsx` first to find its existing mock-client pattern (it must already mock `getCollectionSchema` for the `pkColumn` tests — mirror that exactly). Append a test:

```ts
test("exposes resolvedSource and hasGeometry per source", async () => {
  const client = {
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs" }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: { column: "geometry", type: "Point", srid: 4326 }, fields: [] }),
    queryDataSource: vi.fn().mockResolvedValue([]),
    featuresUrl: vi.fn().mockReturnValue("u"),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sources: DataSource[] = [{ id: "ds1", type: "features", service: "core", layer: "", datasetId: "d1", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    return <p>{s ? `${s.resolvedSource?.id}/${s.hasGeometry}` : "none"}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={sources}><Probe /></DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("ds1/true")).toBeInTheDocument());
});
```

Adjust the exact mock shape/imports (`ItemClientProvider`, `QueryClient`, `render`, `waitFor`, `screen`, `vi`) to match whatever this test file already imports — check with `grep -n "^import" shell/src/builder/DataContext.test.tsx` before writing, since the file already has working scaffolding for a `pkColumn`-style test that this one should sit next to.

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: FAIL — text `"ds1/true"` never appears (`resolvedSource`/`hasGeometry` are `undefined`).

- [ ] **Step 3: Implement**

Edit `shell/src/builder/DataContext.tsx`. Replace the `pkByCollection` computation block:

```ts
  const pkByCollection: Record<string, string> = {};
  collectionIds.forEach((id, i) => {
    const data = schemaResults[i].data;
    if (data) pkByCollection[id] = data.pk;
  });
```

with:

```ts
  const pkByCollection: Record<string, string> = {};
  const hasGeometryByCollection: Record<string, boolean> = {};
  collectionIds.forEach((id, i) => {
    const data = schemaResults[i].data;
    if (data) {
      pkByCollection[id] = data.pk;
      hasGeometryByCollection[id] = data.geometry != null;
    }
  });
```

Then update the `states` construction:

```ts
  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    const merged = mergedQueryFor(s);
    const dataset = s.datasetId ? datasets[s.datasetId] : undefined;
    const hasGeometry = dataset
      ? (dataset.source === "arcgis" ? true : (hasGeometryByCollection[dataset.collectionId] ?? false))
      : false;
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      layer: s.layer,
      url: s.type === "features" ? client.featuresUrl(merged) : undefined,
      datasetId: s.datasetId,
      pkColumn: dataset && dataset.source === "collection" ? pkByCollection[dataset.collectionId] : undefined,
      resolvedSource: merged,
      hasGeometry,
    };
  });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Run the full shell unit suite (check for ripple breakage)**

Run: `cd shell && npm run test`
Expected: all tests pass — `DataSourceState`'s two new optional fields shouldn't break anything, but widget tests constructing `DataSourceState` by hand (e.g. `data.test.tsx`'s `state()` helper) should be checked for `strict` object-literal issues; they use `Partial<DataSourceState>` so adding optional fields is backward compatible.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/DataContext.tsx shell/src/builder/DataContext.test.tsx
git commit -m "feat(shell): SP-16a — DataContext expose resolvedSource/hasGeometry par source"
```

---

### Task 10: Shell — `ExplorerMenu` gains export entries

**Files:**
- Modify: `shell/src/builder/widgets/ExplorerMenu.tsx`
- Modify: `shell/src/builder/widgets/ExplorerMenu.test.tsx`

**Interfaces:**
- Consumes: `DataSourceState.resolvedSource`/`.hasGeometry` (Task 9), `ItemClient.exportDataSource` (Task 8), `useItemClient`.
- Produces: `ExplorerMenu` accepts two new optional props, `resolvedSource?: DataSource` and `hasGeometry?: boolean` — used by Task 11 (the 6 widget call sites).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/ExplorerMenu.test.tsx` (check its existing imports first — it currently imports only `ExplorerProvider`/`useExplorerTarget`; the new tests need `ItemClientProvider` and a fake `ItemClient`):

```tsx
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { DataSource, ItemClient } from "../../api/types";

test("aggregate sources only offer CSV/XLSX", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.getByLabelText("Exporter en XLSX")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});

test("items sources with geometry offer all four formats", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  for (const label of ["Exporter en CSV", "Exporter en XLSX", "Exporter en GEOJSON", "Exporter en GPKG"]) {
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  }
});

test("items sources without geometry only offer CSV/XLSX", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry={false} />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});

test("clicking an export format calls exportDataSource and triggers a download", async () => {
  const blob = new Blob(["a,b\n1,2\n"], { type: "text/csv" });
  const exportDataSource = vi.fn().mockResolvedValue({ blob, filename: "parcs.csv" });
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: { groupBy: "region" } };
  const createObjectURL = vi.fn().mockReturnValue("blob:fake");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry={false} />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(source, "csv");
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("no export entries when resolvedSource is absent (backward compatible with existing callers)", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="s1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.queryByLabelText(/^Exporter en/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: FAIL — `resolvedSource`/`hasGeometry` props don't exist on `ExplorerMenu` yet (TS error) and no export buttons render.

- [ ] **Step 3: Implement**

Rewrite `shell/src/builder/widgets/ExplorerMenu.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";
import { useItemClient } from "../../api/ItemClientProvider";
import type { DataSource } from "../../api/types";

const AGGREGATE_FORMATS = ["csv", "xlsx"];
const ITEMS_FORMATS_WITH_GEOMETRY = ["csv", "xlsx", "geojson", "gpkg"];
const ITEMS_FORMATS_WITHOUT_GEOMETRY = ["csv", "xlsx"];

function formatsFor(source: DataSource, hasGeometry: boolean): string[] {
  if (source.type === "statistics") return AGGREGATE_FORMATS;
  return hasGeometry ? ITEMS_FORMATS_WITH_GEOMETRY : ITEMS_FORMATS_WITHOUT_GEOMETRY;
}

export function ExplorerMenu({
  datasetId, dataSourceId, resolvedSource, hasGeometry,
}: {
  datasetId: string | undefined;
  dataSourceId: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
}) {
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const client = useItemClient();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!enabled || !datasetId) return null;

  const formats = resolvedSource ? formatsFor(resolvedSource, Boolean(hasGeometry)) : [];

  async function handleExport(format: string) {
    if (!resolvedSource) return;
    setMenuOpen(false);
    const { blob, filename } = await client.exportDataSource(resolvedSource, format);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label="Explorer"
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        onClick={() => setMenuOpen((v) => !v)}
      >
        ⋮
      </button>
      {menuOpen && (
        <div className="absolute right-0 top-full mt-1 whitespace-nowrap rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-sm">
          <button
            type="button"
            aria-label="Voir les entités"
            className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
            onClick={() => {
              setMenuOpen(false);
              open({ datasetId, dataSourceId });
            }}
          >
            Voir les entités
          </button>
          {formats.map((format) => (
            <button
              key={format}
              type="button"
              aria-label={`Exporter en ${format.toUpperCase()}`}
              className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => handleExport(format)}
            >
              Exporter en {format.toUpperCase()}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/ExplorerMenu.tsx shell/src/builder/widgets/ExplorerMenu.test.tsx
git commit -m "feat(shell): SP-16a — ExplorerMenu gagne des entrées d'export (CSV/XLSX/GeoJSON/GPKG)"
```

---

### Task 11: Shell — wire `resolvedSource`/`hasGeometry` through the 6 widget call sites

**Files:**
- Modify: `shell/src/builder/widgets/chart.tsx` (2 call sites)
- Modify: `shell/src/builder/widgets/data.tsx` (2 call sites)
- Modify: `shell/src/builder/widgets/indicator.tsx` (1 call site)
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (1 call site)
- Modify: `shell/src/builder/widgets/pivot.tsx` (1 call site)

**Interfaces:**
- Consumes: `ExplorerMenu`'s new props (Task 10), each widget's own already-in-scope `data`/`ctx.data` variable (a `DataSourceState`, now carrying `resolvedSource`/`hasGeometry` per Task 9).
- Produces: nothing new — this task only makes the feature reachable from the UI. Behavior is already covered by Task 10's unit tests; Task 13's E2E test exercises one concrete path end-to-end.

This is six mechanical one-line edits — same pattern each time: add `resolvedSource={data.resolvedSource}` and `hasGeometry={data.hasGeometry}` (or `ctx.data?.resolvedSource`/`ctx.data?.hasGeometry` where the call site already uses `ctx.data?.` directly) to the existing `<ExplorerMenu ... />` call.

- [ ] **Step 1: `chart.tsx`, compare-mode branch**

In `shell/src/builder/widgets/chart.tsx`, find (around line 230):

```tsx
            <ExplorerMenu datasetId={datasetId} dataSourceId={originSourceId} />
```

Replace with:

```tsx
            <ExplorerMenu datasetId={datasetId} dataSourceId={originSourceId} resolvedSource={data?.resolvedSource} hasGeometry={data?.hasGeometry} />
```

- [ ] **Step 2: `chart.tsx`, default (non-compare) branch**

Find (around line 250):

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={originSourceId} />
```

Replace with:

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={originSourceId} resolvedSource={data.resolvedSource} hasGeometry={data.hasGeometry} />
```

- [ ] **Step 3: `data.tsx`, list widget**

Find (around line 63):

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
```

Replace with:

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} resolvedSource={data.resolvedSource} hasGeometry={data.hasGeometry} />
```

- [ ] **Step 4: `data.tsx`, table widget**

Find the second occurrence (around line 196), same replacement as Step 3.

- [ ] **Step 5: `indicator.tsx`**

Find (around line 208):

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
```

Replace with:

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} resolvedSource={data.resolvedSource} hasGeometry={data.hasGeometry} />
```

- [ ] **Step 6: `mapWidget.tsx`**

Find (around line 173):

```tsx
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
```

Replace with:

```tsx
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} resolvedSource={ctx.data?.resolvedSource} hasGeometry={ctx.data?.hasGeometry} />
```

- [ ] **Step 7: `pivot.tsx`**

Find (around line 74):

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={dataSourceId} />
```

Replace with:

```tsx
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={dataSourceId} resolvedSource={data.resolvedSource} hasGeometry={data.hasGeometry} />
```

- [ ] **Step 8: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all tests pass — no test asserts on `ExplorerMenu`'s exact prop list from these call sites, so no existing test should break.

- [ ] **Step 9: Run the type check**

Run: `cd shell && npm run build`
Expected: no TypeScript errors.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/data.tsx shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/pivot.tsx
git commit -m "feat(shell): SP-16a — branche resolvedSource/hasGeometry sur les 6 widgets analytiques"
```

---

### Task 12: Shell — `DatasetEditPage` export section

**Files:**
- Modify: `shell/src/pages/DatasetEditPage.tsx`
- Modify: `shell/src/pages/DatasetEditPage.test.tsx`

**Interfaces:**
- Consumes: `ItemClient.exportDataSource` (Task 8), `draft.source` / `schemaQuery.data?.geometry` (already resolved in this page).

- [ ] **Step 1: Write the failing test**

`shell/src/pages/DatasetEditPage.test.tsx` already defines module-level `item`/`datasetConfig`/`schema` fixtures and a `renderPage(client: Partial<ItemClient>)` helper that renders `<DatasetEditPage pk="ds-1" />` — every test must supply the full set of methods the page calls during load (`getItem`, `getDatasetConfig`, `getCollectionSchema`, `saveDatasetConfig`, `updateItem`), same as the file's existing `"loads the dataset, shows merged columns..."` test. Append, reusing the module-level `item`/`datasetConfig` consts and a locally-adjusted `schema`:

```tsx
test("offers CSV/XLSX/GeoJSON/GPKG export when the collection has geometry, and downloads on click", async () => {
  const blob = new Blob(["a,b\n1,2\n"], { type: "text/csv" });
  const exportDataSource = vi.fn().mockResolvedValue({ blob, filename: "villes.csv" });
  const createObjectURL = vi.fn().mockReturnValue("blob:fake");
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });

  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue({ ...schema, geometry: { column: "geometry", type: "Point", srid: 4326 } }),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
    exportDataSource,
  });

  await screen.findByText(/Dataset partagé/);
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(
    expect.objectContaining({ type: "features", datasetId: "ds-1", query: {} }), "csv",
  );
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("only offers CSV/XLSX when the collection has no geometry", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema), // schema.geometry is already null
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
  });
  await screen.findByText(/Dataset partagé/);
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: FAIL — `Exporter en CSV` label not found.

- [ ] **Step 3: Implement**

Edit `shell/src/pages/DatasetEditPage.tsx`. Add near the top of the component body, after `const merged = ...` line:

```tsx
  const hasGeometry = draft.source === "arcgis" ? true : Boolean(schemaQuery.data?.geometry);
  const exportFormats = hasGeometry ? ["csv", "xlsx", "geojson", "gpkg"] : ["csv", "xlsx"];

  async function handleExport(format: string) {
    const source = { id: "__dataset-export__", type: "features" as const, service: "core", layer: "", datasetId: pk, query: {} };
    const { blob, filename } = await client.exportDataSource(source, format);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
```

Then add a section in the JSX, right before the final `<Button size="sm" ...>Enregistrer les colonnes</Button>`:

```tsx
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-slate-500">Export</p>
        <div className="flex gap-2">
          {exportFormats.map((format) => (
            <button
              key={format}
              type="button"
              aria-label={`Exporter en ${format.toUpperCase()}`}
              className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
              onClick={() => handleExport(format)}
            >
              {format.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
```

Check `DataSource`'s `type` field literal union includes `"features"` (used elsewhere, e.g. `ExplorerDrawer.tsx`'s `type: "features"`) — no new type needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx
git commit -m "feat(shell): SP-16a — section Export sur DatasetEditPage (non filtré, formats selon géométrie)"
```

---

### Task 13: E2E — `dataset-export.spec.ts`

**Files:**
- Create: `shell/e2e/dataset-export.spec.ts`

**Interfaces:**
- Consumes: `mockCore` from `./mocks` — same conventions as `shell/e2e/analytics-context.spec.ts` (already read in full while writing this plan; its `createApp`/`addFeaturesSource`/`promoteLastSource` helpers and mock-route shapes for `**/collections`, `**/collections/{id}/schema`, `**/collections/{id}/items*`, `**/configs/by-item/dataset-1`, `https://core.test/items/dataset-1` are reused verbatim below — this is not a guess, it's copied from that file's scenario 10 ("voir les entités") and scenario 2 (dataset-creation-dialog flow)).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/dataset-export.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0

import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// Mêmes conventions que analytics-context.spec.ts (SP-14b/14d) : construit
// l'app via la vraie UI du builder, jamais en injectant du JSON brut.

async function createApp(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill(title);
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

async function addFeaturesSource(page: Page, collection: string) {
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).last().fill(collection);
}

async function promoteLastSource(page: Page, expectedActiveCount: number) {
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).last().click();
  await expect(page.getByText("Dataset partagé actif")).toHaveCount(expectedActiveCount);
}

test("exporter un widget table en CSV depuis une app en mode runtime", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "analytics", pk: "id",
        geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "region", type: "string" }],
      },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [{ id: 1, properties: { region: "Nord" } }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } },
      },
    });
  });
  await page.route("**/collections/analytics/export/items*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("format")).toBe("csv");
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="analytics.csv"' },
      body: "region\nNord\n",
    });
  });

  await createApp(page, "Export table");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Explorer" }).click();
  await page.getByRole("button", { name: "Exporter en CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("analytics.csv");
});

test("exporter depuis DatasetEditPage en XLSX", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [{
          id: "villes", title: "Villes", description: "", tableName: "villes", isPublic: true, editable: true,
          geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 1, owner: "mockuser",
        }],
      },
    });
  });
  await page.route("**/collections/villes/schema", async (route) => {
    await route.fulfill({
      json: { collection: "villes", pk: "id", geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "nom", type: "string" }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "villes", columns: {} } },
      },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Villes partagées", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });
  await page.route("**/collections/villes/export/items*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("format")).toBe("xlsx");
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="villes.xlsx"',
      },
      body: Buffer.from("fake-xlsx-bytes"),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("villes");
  await dialog.getByLabel("Titre").fill("Villes partagées");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter en XLSX" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("villes.xlsx");
});
```

- [ ] **Step 2: Run it**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test dataset-export.spec.ts`
Expected: PASS (2 tests). If a selector doesn't match (e.g. the dataset-creation dialog's exact field labels drift from what's shown above), cross-check against the live equivalents in `shell/e2e/analytics-context.spec.ts` scenario 2 (`setupTimeFieldDatasetAndApp`) and scenario 10 (`voir les entités`) rather than guessing.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: all specs pass (18 existing + this new one = 19)

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/dataset-export.spec.ts
git commit -m "test(e2e): SP-16a — export CSV depuis un widget table, export XLSX depuis DatasetEditPage"
```

---

## Final check

- [ ] Run `cd core && uv run pytest -q` — full core suite green.
- [ ] Run `cd shell && npm run test && npm run build && npm run e2e` — full shell suite green.
- [ ] Re-read `docs/superpowers/specs/2026-08-07-sp16a-export-serveur-design.md` section by section and confirm every section (§2-§8) has a corresponding task above.
