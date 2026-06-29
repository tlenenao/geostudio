# Builder Service Symmetric Delete (SP-0b.2-a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add symmetric deletion to the Builder Service so deleting an App/Dashboard removes both its config (and revisions) and the linked GeoNode item, via a new `DELETE /configs/{id}` endpoint and an `ItemClient.delete_item` port method.

**Architecture:** Extend the existing FastAPI Builder Service (delivered in SP-0a). The `ItemClient` port gains `delete_item`; the repository gains `delete_config` (removes the `Config` and its `ConfigRevision` rows); a new `DELETE /configs/{id}` route orchestrates: look up the linked `item_id`, call `items.delete_item`, then `repo.delete_config`. The existing contract (POST/GET/PUT/revisions/rollback) is unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, httpx, uv. Tests use in-memory SQLite + MSW-style httpx MockTransport.

## Global Constraints

- Work entirely under `builder-service/`; run tests with `uv run pytest` from that directory.
- Python floor 3.12; keep pytest output pristine (`filterwarnings = ["error", ...]` is configured; in-memory SQLite engines in test fixtures are disposed after `yield`).
- The existing contract (`ConfigRead`, `POST/GET/PUT /configs`, `/revisions`, `/rollback`, `ItemClient.create_item`) must NOT change — only additions.
- GeoNode access stays inside `app/geonode.py` only.
- Deletion must leave no orphan: a successful delete removes the config, its revisions, and the GeoNode item.
- Stage only the files each task lists (explicit paths); never stage `__pycache__`.

---

### Task 1: Extend `ItemClient` with `delete_item` (port + stub + HTTP adapter)

**Files:**
- Modify: `builder-service/app/geonode.py`
- Test: `builder-service/tests/test_geonode.py` (add cases)
- Test: `builder-service/tests/test_geonode_http.py` (add cases)

**Interfaces:**
- Consumes: existing `ItemClient` Protocol, `StubItemClient`, `GeoNodeItemClient(base_url, token, http=None)`.
- Produces:
  - `ItemClient.delete_item(self, item_id: str) -> None` added to the Protocol.
  - `StubItemClient.delete_item` records ids in `self.deleted: list[str]` (initialized in `__init__`).
  - `GeoNodeItemClient.delete_item` issues `DELETE {base_url}/api/v2/resources/{item_id}` with `Authorization: Bearer {token}` and calls `raise_for_status()`.

- [ ] **Step 1: Write the failing stub test**

Add to `builder-service/tests/test_geonode.py`:

```python
def test_stub_delete_item_records_call():
    client = StubItemClient()
    item_id = client.create_item(title="X", type="app", owner="alice")
    client.delete_item(item_id)
    assert client.deleted == [item_id]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_geonode.py::test_stub_delete_item_records_call -v`
Expected: FAIL — `AttributeError: 'StubItemClient' object has no attribute 'deleted'` (or `delete_item`).

- [ ] **Step 3: Extend the port and stub in `app/geonode.py`**

In the `ItemClient` Protocol, add below `create_item`:

```python
    def delete_item(self, item_id: str) -> None:
        """Delete the linked item in the content backend."""
        ...
```

In `StubItemClient.__init__`, add `self.deleted: list[str] = []` (keep the existing `self.created`). Add the method:

```python
    def delete_item(self, item_id: str) -> None:
        self.deleted.append(item_id)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_geonode.py -v`
Expected: PASS (existing + new test).

- [ ] **Step 5: Write the failing HTTP-adapter test**

Add to `builder-service/tests/test_geonode_http.py`:

```python
def test_geonode_client_delete_item_issues_delete_with_auth():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = GeoNodeItemClient(base_url="https://geonode.example", token="t0ken", http=http)

    client.delete_item("42")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://geonode.example/api/v2/resources/42"
    assert captured["auth"] == "Bearer t0ken"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/test_geonode_http.py::test_geonode_client_delete_item_issues_delete_with_auth -v`
Expected: FAIL — `AttributeError: 'GeoNodeItemClient' object has no attribute 'delete_item'`.

- [ ] **Step 7: Add the adapter method to `GeoNodeItemClient` in `app/geonode.py`**

```python
    def delete_item(self, item_id: str) -> None:
        response = self._http.delete(
            f"{self._base_url}/api/v2/resources/{item_id}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
```

- [ ] **Step 8: Run the geonode suites**

Run: `uv run pytest tests/test_geonode.py tests/test_geonode_http.py -v`
Expected: PASS (all).

- [ ] **Step 9: Commit**

```bash
git add builder-service/app/geonode.py builder-service/tests/test_geonode.py builder-service/tests/test_geonode_http.py
git commit -m "feat(builder-service): add ItemClient.delete_item (port, stub, HTTP adapter)"
```

---

### Task 2: Repository `delete_config`

**Files:**
- Modify: `builder-service/app/repository.py`
- Test: `builder-service/tests/test_repository.py` (add cases)

**Interfaces:**
- Consumes: `Config`, `ConfigRevision` from `app.models`; the existing `create_config`/`update_config` helpers and the `session` test fixture.
- Produces: `delete_config(session: Session, config_id: str) -> bool` — deletes the `Config` and all its `ConfigRevision` rows; returns `True` if a config was deleted, `False` if none existed. Revisions are deleted before the config (FK-safe).

- [ ] **Step 1: Write the failing tests**

Add to `builder-service/tests/test_repository.py`:

```python
def test_delete_config_removes_config_and_revisions(session):
    created = repo.create_config(session, _config(widget="map"), item_id="item-1")
    repo.update_config(session, created.id, _config(widget="table"))

    assert repo.delete_config(session, created.id) is True
    assert repo.get_config(session, created.id) is None
    assert repo.list_revisions(session, created.id) == []


def test_delete_missing_config_returns_false(session):
    assert repo.delete_config(session, "nope") is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_repository.py -k delete -v`
Expected: FAIL — `AttributeError: module 'app.repository' has no attribute 'delete_config'`.

- [ ] **Step 3: Implement `delete_config` in `app/repository.py`**

Add `delete` to the SQLAlchemy import (the file already imports `select`):

```python
from sqlalchemy import delete, select
```

Add the function:

```python
def delete_config(session: Session, config_id: str) -> bool:
    record = session.get(Config, config_id)
    if record is None:
        return False
    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.delete(record)
    session.commit()
    return True
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/repository.py builder-service/tests/test_repository.py
git commit -m "feat(builder-service): add repository.delete_config (config + revisions)"
```

---

### Task 3: `DELETE /configs/{id}` route

**Files:**
- Modify: `builder-service/app/routes.py`
- Test: `builder-service/tests/test_routes.py` (add cases)

**Interfaces:**
- Consumes: `repository.delete_config`, `ItemClient.delete_item`, the existing `get_session`/`get_item_client` dependencies, the existing `client` test fixture (which exposes `client.stub`).
- Produces: `DELETE /configs/{config_id}` → looks up the `Config`; if absent returns `404`; otherwise, if it has a linked `item_id`, calls `items.delete_item(item_id)`, then `repo.delete_config`, and returns `204` with an empty body.

- [ ] **Step 1: Write the failing tests**

Add to `builder-service/tests/test_routes.py`:

```python
def test_delete_config_removes_it_and_deletes_linked_item(client):
    created = _create(client)
    config_id = created["id"]
    item_id = created["itemId"]

    response = client.delete(f"/configs/{config_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.stub.deleted == [item_id]
    assert client.get(f"/configs/{config_id}").status_code == 404


def test_delete_missing_config_returns_404(client):
    assert client.delete("/configs/nope").status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_routes.py -k delete -v`
Expected: FAIL — 405 Method Not Allowed (no DELETE route yet) / assertion error.

- [ ] **Step 3: Add the route to `app/routes.py`**

Add `Response` and `status` to the FastAPI import (the file already imports `APIRouter, Depends, HTTPException`); ensure the import line reads:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
```

Add the import of the ORM model at the top (alongside existing imports):

```python
from app.models import Config
```

Add the endpoint:

```python
@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
) -> Response:
    record = session.get(Config, config_id)
    if record is None:
        raise HTTPException(status_code=404, detail="config not found")
    if record.item_id:
        items.delete_item(record.item_id)
    repo.delete_config(session, config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/test_routes.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, output pristine.

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/routes.py builder-service/tests/test_routes.py
git commit -m "feat(builder-service): add DELETE /configs/{id} (config + linked item)"
```

---

## Self-Review

**Spec coverage (against SP-0b.2 §3 — backend change):**
- `ItemClient.delete_item` (port + stub + HTTP adapter) → Task 1. ✅
- `repository.delete_config` (config + revisions, bool) → Task 2. ✅
- `DELETE /configs/{id}` (lookup item_id → delete_item → delete_config; 204/404) → Task 3. ✅
- No orphan after delete (revisions + config + GeoNode item all removed) → Tasks 2+3. ✅
- Existing contract unchanged (only additions) → no edits to create/get/update/revisions/rollback. ✅

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `delete_item(self, item_id: str) -> None` identical across Protocol (Task 1), `StubItemClient` (Task 1), `GeoNodeItemClient` (Task 1), and the route call site (Task 3). `delete_config(session, config_id) -> bool` defined in Task 2 and called in Task 3. The `client` fixture's `client.stub` (from SP-0a Task 6) exposes the `StubItemClient`, now with `.deleted`. ✅

## Notes for SP-0b.2-b / SP-0b.2-c (front)

- `item-client.deleteItem(configId)` will call this `DELETE /configs/{configId}`.
- `createConfigItem` uses the existing `POST /configs`; `updateItem`/`uploadThumbnail` hit GeoNode directly (not this service).
