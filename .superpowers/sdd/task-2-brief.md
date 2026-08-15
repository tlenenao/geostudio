### Task 2: `duckdb_conn.open_local_connection()`

**Files:**
- Modify: `core/app/analytics/duckdb_conn.py`
- Modify: `core/tests/test_analytics_duckdb_conn.py`

**Interfaces:**
- Produces: `open_local_connection() -> duckdb.DuckDBPyConnection` — loads
  only the `spatial` extension (no `httpfs`, no `h3`, no S3 `SET`
  statements). Used exclusively by the mini-server (Tasks 5/6), which only
  ever reads local files.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_analytics_duckdb_conn.py` (existing content and
`_RecordingConnection` stay as-is above this):

```python


def test_open_local_connection_installs_and_loads_spatial_only(monkeypatch):
    import duckdb

    from app.analytics.duckdb_conn import open_local_connection

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_local_connection()

    joined = "\n".join(recording.statements)
    assert "INSTALL spatial" in joined and "LOAD spatial" in joined
    assert "httpfs" not in joined
    assert "s3_" not in joined
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v`
Expected: FAIL with `ImportError: cannot import name 'open_local_connection'`

- [ ] **Step 3: Add `open_local_connection` to `duckdb_conn.py`**

In `core/app/analytics/duckdb_conn.py`, append after `open_spatial_connection`:

```python


def open_local_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour le mini-serveur autoporté (SP-18c) :
    lit un instantané GeoParquet local (jamais S3/MinIO) — seule l'extension
    spatial est nécessaire (ST_Intersects/ST_MakeEnvelope/ST_AsGeoJSON/
    ST_GeomFromGeoJSON), aucune configuration s3_* requise."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/duckdb_conn.py core/tests/test_analytics_duckdb_conn.py
git commit -m "feat(core): open_local_connection for the standalone mini-server (SP-18c)"
```

---

