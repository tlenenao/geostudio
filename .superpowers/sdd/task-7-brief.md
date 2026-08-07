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

