### Task 9: widen `_SUPPORTED_MODES` on the routes

**Files:**
- Modify: `core/app/appexport/routes.py`
- Modify: `core/tests/test_appexport_routes.py`

**Interfaces:**
- Produces: `POST /app-exports` now accepts `mode: "static" | "connected" |
  "standalone"`.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_routes.py`:

```python


def test_post_app_export_accepts_standalone_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "standalone"})
    assert response.status_code == 202
    assert len(calls) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: `test_post_app_export_accepts_standalone_mode` FAILS with `422`.

- [ ] **Step 3: Widen `_SUPPORTED_MODES` in `routes.py`**

In `core/app/appexport/routes.py`, change:

```python
_SUPPORTED_MODES = {"static", "connected"}  # "standalone" arrive en SP-18c
```

to:

```python
_SUPPORTED_MODES = {"static", "connected", "standalone"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/routes.py core/tests/test_appexport_routes.py
git commit -m "feat(core): POST /app-exports accepts mode=standalone (SP-18c)"
```

---

