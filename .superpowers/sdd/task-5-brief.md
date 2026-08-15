### Task 5: `app.appexport.miniserver.items` — DuckDB-backed features listing

**Files:**
- Create: `core/app/appexport/miniserver/__init__.py`
- Create: `core/app/appexport/miniserver/items.py`
- Create: `core/tests/test_appexport_miniserver_items.py`

**Interfaces:**
- Consumes: `open_local_connection` (Task 2), `TableInfo`/`ColumnInfo`
  (`app.collections.introspection`, unchanged), `ChangeRow`/`write_geoparquet`
  (`app.cdc.parquet_writer`, used only by the test fixture here, mirroring
  what Task 4's writer produces).
- Produces: `FeaturePage` dataclass (`features: list[dict]`,
  `number_matched: int`, `number_returned: int`),
  `select_features(conn, *, base_uri, tenant_id, collection_id, table_info,
  limit, offset, bbox=None, geom_intersects=None) -> FeaturePage`,
  `get_feature(conn, *, base_uri, tenant_id, collection_id, table_info,
  fid: str) -> dict | None`. Mirrors `app.features.repository`'s function
  names/shapes (same `FeatureCollection`-ready output), reading via DuckDB
  SQL against a local GeoParquet snapshot instead of Postgres. Consumed by
  Task 6's `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/app/appexport/miniserver/__init__.py` (empty file):

```python
```

Create `core/tests/test_appexport_miniserver_items.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.miniserver.items import get_feature, select_features
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _write_fixture(tmp_path, *, tenant_id="t1", collection_id="col1"):
    rows = [
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=1,
                  columns={"name": "Alpha"}, geometry_column=None, geometry_wkb_hex=None),
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=2,
                  columns={"name": "Beta"}, geometry_column=None, geometry_wkb_hex=None),
    ]
    parquet_dir = tmp_path / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(rows, srid=4326, path=str(parquet_dir / "data.parquet"))
    return TableInfo(
        table_name="t_x", pk_column="id", geometry_column=None, geometry_type=None, srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )


def test_select_features_reads_snapshot(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=10, offset=0,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert sorted(f["properties"]["name"] for f in page.features) == ["Alpha", "Beta"]
    assert all(f["type"] == "Feature" for f in page.features)


def test_select_features_paginates(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=1, offset=1,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert page.number_returned == 1


def test_select_features_missing_collection_returns_empty_page(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="ghost",
            table_info=table_info, limit=10, offset=0,
        )
    finally:
        conn.close()
    assert page.features == []
    assert page.number_matched == 0


def test_get_feature_returns_single_row(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="2",
        )
    finally:
        conn.close()
    assert feature["properties"]["name"] == "Beta"


def test_get_feature_missing_returns_none(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="999",
        )
    finally:
        conn.close()
    assert feature is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_items.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.miniserver.items'`

- [ ] **Step 3: Create `items.py`**

Create `core/app/appexport/miniserver/items.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Lecture des features via DuckDB contre un instantané GeoParquet local
(SP-18c) — mirroir de app.features.repository (mêmes noms de fonctions, même
forme de sortie FeatureCollection-ready), mais via SQL DuckDB au lieu de
SQL Postgres paramétré : app.features.repository est Postgres-only,
inutilisable dans le mini-serveur (pas de driver Postgres dans cette
image). Même glob hive-partitionné que app.analytics.aggregate (tenant_id=/
collection_id=/dt=*/*.parquet) — Task 4's write_snapshot écrit exactement
cette disposition."""
import json
from dataclasses import dataclass

from app.collections.introspection import TableInfo


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int
    number_returned: int


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _glob(base_uri: str, tenant_id: str, collection_id: str) -> str:
    return f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"


def _has_any_file(conn, base_uri: str, tenant_id: str, collection_id: str) -> bool:
    glob = _glob(base_uri, tenant_id, collection_id)
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _property_columns(info: TableInfo) -> list:
    return [c for c in info.columns if c.name not in (info.pk_column, "tenant_id", info.geometry_column)]


def _select_list(info: TableInfo) -> str:
    cols = [_qi(info.pk_column)]
    cols += [_qi(c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"ST_AsGeoJSON({_qi(info.geometry_column)}) AS __geo")
    return ", ".join(cols)


def _row_to_feature(info: TableInfo, row: dict) -> dict:
    props = {c.name: row[c.name] for c in _property_columns(info)}
    geometry = None
    if info.geometry_column and row.get("__geo"):
        geometry = json.loads(row["__geo"])
    return {"type": "Feature", "id": row[info.pk_column], "geometry": geometry, "properties": props}


def _fetch_rows(conn, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in result]


def _build_where(table_info: TableInfo, bbox, geom_intersects) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_MakeEnvelope(?, ?, ?, ?))")
        params.extend([minx, miny, maxx, maxy])
    if geom_intersects is not None:
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_GeomFromGeoJSON(?))")
        params.append(json.dumps(geom_intersects))
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _coerce_fid(table_info: TableInfo, fid: str):
    pk = next((c for c in table_info.columns if c.name == table_info.pk_column), None)
    if pk is not None and pk.type == "integer":
        try:
            return int(fid)
        except ValueError:
            return None
    return fid


def select_features(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo,
    limit: int, offset: int, bbox=None, geom_intersects=None,
) -> FeaturePage:
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return FeaturePage(features=[], number_matched=0, number_returned=0)
    glob = _glob(base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(table_info, bbox, geom_intersects)
    count_sql = f"SELECT COUNT(*) FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) {where_sql}"
    matched = conn.execute(count_sql, where_params).fetchone()[0]
    sql = (
        f"SELECT {_select_list(table_info)} FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"{where_sql} ORDER BY {_qi(table_info.pk_column)} LIMIT ? OFFSET ?"
    )
    rows = _fetch_rows(conn, sql, [*where_params, limit, offset])
    features = [_row_to_feature(table_info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched, number_returned=len(features))


def get_feature(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo, fid: str,
) -> dict | None:
    value = _coerce_fid(table_info, fid)
    if value is None or not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return None
    glob = _glob(base_uri, tenant_id, collection_id)
    sql = (
        f"SELECT {_select_list(table_info)} FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"WHERE {_qi(table_info.pk_column)} = ?"
    )
    rows = _fetch_rows(conn, sql, [value])
    return _row_to_feature(table_info, rows[0]) if rows else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_items.py -v`
Expected: PASS (5 tests) — no `CORE_TEST_DATABASE_URL` needed, pure DuckDB/local files.

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/miniserver/__init__.py core/app/appexport/miniserver/items.py core/tests/test_appexport_miniserver_items.py
git commit -m "feat(core): mini-server DuckDB-backed features listing (SP-18c)"
```

---

