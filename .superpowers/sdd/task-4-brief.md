### Task 4: widen `_SUPPORTED_MODES` on the routes

**Files:**
- Modify: `core/app/appexport/routes.py`
- Modify: `core/tests/test_appexport_routes.py`

**Interfaces:**
- Produces: `POST /app-exports` now accepts `mode: "static" | "connected"` (was `"static"` only).

- [ ] **Step 1: Update the existing invalid-mode test, write the new accepted-mode test**

In `core/tests/test_appexport_routes.py`, replace
`test_post_app_export_rejects_invalid_mode` (the comment and the mode value
both change — `"connected"` is no longer invalid):

```python
def test_post_app_export_rejects_invalid_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "bogus"})
    assert response.status_code == 422
```

Then append a new test at the end of the file:

```python


def test_post_app_export_accepts_connected_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "connected"})
    assert response.status_code == 202
    assert len(calls) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: `test_post_app_export_rejects_invalid_mode` still PASSES (`"bogus"`
was already rejected by the old `_SUPPORTED_MODES = {"static"}`).
`test_post_app_export_accepts_connected_mode` FAILS with `422` instead of
`202` (`"connected"` not yet in `_SUPPORTED_MODES`).

- [ ] **Step 3: Widen `_SUPPORTED_MODES` in `routes.py`**

In `core/app/appexport/routes.py`, change:

```python
_SUPPORTED_MODES = {"static"}  # "connected"/"standalone" arrivent en SP-18b/c
```

to:

```python
_SUPPORTED_MODES = {"static", "connected"}  # "standalone" arrive en SP-18c
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/routes.py core/tests/test_appexport_routes.py
git commit -m "feat(core): POST /app-exports accepts mode=connected (SP-18b)"
```

---

