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

