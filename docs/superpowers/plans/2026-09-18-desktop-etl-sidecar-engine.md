# Desktop ETL — moteur sidecar + API loopback (Phase E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the future desktop-etl Tauri shell a pure-Python, Postgres-free,
procrastinate-free HTTP loopback API that replays the shape of the core's
pipeline endpoints (`GET /pipelines/ops`, `POST /pipelines/{itemId}/run`,
`GET /pipelines/{itemId}/runs`, `POST /pipelines/{itemId}/preview`, plus a
new `PUT /pipelines/{itemId}` to hand it the active payload) by calling
`app.pipelines.runtime.run_pipeline()`/`preview_pipeline()` directly with
`session=None`.

**Architecture:** New `core/app/pipelines/sidecar/` sub-package: an
in-memory `RunTracker` implementation (satisfies the existing `RunTracker`
Protocol from `jobs.py`) + an in-memory `PipelineStore` + a background-thread
runner (mirrors `run_pipeline_task`'s engine call and error handling, minus
every Postgres/S3/notification touchpoint) + a small FastAPI app assembling
the four routes. A new `core/scripts/pipeline_sidecar.py` entrypoint binds an
ephemeral loopback port and prints it on stdout (handshake for a future
Tauri parent process, Phase G) before serving. Entirely testable today on
Linux via `httpx.ASGITransport` — no Tauri, no Windows, no PyInstaller
freeze of the real geospatial dependencies (that's Phase F).

**Tech Stack:** Python 3.12, FastAPI (already a hard dependency,
`fastapi>=0.111`), uvicorn (`uvicorn[standard]>=0.30`, installed `0.49.0`),
pytest + `httpx.ASGITransport` (`httpx>=0.27`, already a dependency),
`app.pipelines.runtime`/`app.pipelines.ops.contracts` (existing, reused
as-is).

## Global Constraints

- Every new/modified Python file starts with `# SPDX-License-Identifier: Apache-2.0`.
- No Postgres `Session`, no `procrastinate`, no S3/boto3 client, and no
  FastAPI `Depends(get_session)`/`Depends(get_current_user)` anywhere in
  `core/app/pipelines/sidecar/` — that is the entire point of this phase.
  If a task needs one of these, the task is wrong; stop and re-read
  `docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md` §3.1.
- `runtime.run_pipeline()`/`runtime.preview_pipeline()` are called with
  `session=None, user=None, tenant_id="local"` — verified safe today only
  for graphs made of `reader.file`/transform/`writer.file` nodes (no
  `collectionId`, no `reader.connector.*`); this package must never be
  extended to other op kinds without re-verifying `_prepare()`'s session
  usage first (roadmap §1, "Phase I").
- `CORE_PIPELINE_FILE_IO_ENABLED` must read as enabled for every request
  this package serves — the sidecar sets `os.environ["CORE_PIPELINE_FILE_IO_ENABLED"] = "true"`
  itself at app-creation time (design: "actives par défaut côté sidecar
  desktop"); it must never rely on the caller's shell environment already
  having it set.
- Route response shapes (field names, casing, HTTP status codes) must
  match `core/app/pipelines/routes.py`'s `RunResponse`/`RunStatus` Pydantic
  models and `shell/src/api/types.ts`'s `PipelineRun`/`PipelineOpsCatalog`
  TypeScript types **exactly** — a future Phase G `ItemClient` depends on
  byte-for-byte shape parity to avoid touching `shell/src/builder/pipeline/*`.
- Run `cd core && uv run pytest tests/test_pipeline_sidecar_*.py -v` after
  every task; run the **full** `uv run pytest` + `uv run ruff check .` +
  `uv run ruff format --check .` + `uv run lint-imports` before the final
  commit of the last task (Task 5), matching this repo's closing ritual for
  every prior desktop-etl plan.
- If `/tmp/pytest-of-<user>` is not owned by the current user (a known WSL
  artifact of a prior root-owned Docker run, unrelated to this code), pass
  `--basetemp=<a writable scratch dir>` to pytest instead of investigating
  it as a regression.

---

## File Structure

- **Create** `core/app/pipelines/sidecar/__init__.py` — empty, marks the
  package.
- **Create** `core/app/pipelines/sidecar/tracker.py` — `RunRegistry` (an
  in-memory, thread-safe store of run records per `item_id`) and
  `InMemoryRunTracker` (implements the `RunTracker` Protocol from
  `core/app/pipelines/jobs.py:144-152` against one `RunRegistry` entry).
- **Create** `core/app/pipelines/sidecar/runner.py` — `PipelineStore` (an
  in-memory `item_id -> PipelinePayload` map) and `start_run()` (spawns a
  background thread that calls `runtime.run_pipeline()`, mirroring
  `jobs.py`'s `run_pipeline_task` error handling).
- **Create** `core/app/pipelines/sidecar/app.py` — `create_sidecar_app()`,
  a `fastapi.FastAPI` factory wiring the 5 routes from
  `docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md` §3.1.
- **Create** `core/scripts/pipeline_sidecar.py` — the real entrypoint
  (promotes the throwaway `core/scripts/pipeline_sidecar_spike.py`
  freeze-only script into something Phase F/G actually ship): binds an
  ephemeral `127.0.0.1` port, prints `PORT=<n>` on stdout, serves
  `create_sidecar_app()` via uvicorn until stdin closes or it is killed.
- **Create** `core/tests/test_pipeline_sidecar_tracker.py`,
  `core/tests/test_pipeline_sidecar_runner.py`,
  `core/tests/test_pipeline_sidecar_app.py`,
  `core/tests/test_pipeline_sidecar_entrypoint.py`.

---

### Task 1: `RunRegistry` + `InMemoryRunTracker`

**Files:**
- Create: `core/app/pipelines/sidecar/__init__.py`
- Create: `core/app/pipelines/sidecar/tracker.py`
- Test: `core/tests/test_pipeline_sidecar_tracker.py`

**Interfaces:**
- Consumes: `RunTracker` Protocol, `core/app/pipelines/jobs.py:144-152`
  (`mark_running() -> None`, `mark_succeeded(node_stats: dict) -> None`,
  `mark_failed(error: str) -> None`).
- Produces (for Task 2/3):
  - `class RunRegistry` with:
    - `create(self, item_id: str) -> str` — allocates a `run_id`
      (`uuid.uuid4().hex`), stores a record
      `{"id": run_id, "status": "queued", "startedAt": None, "finishedAt": None, "error": None, "nodeStats": {}}`
      under `item_id`, returns `run_id`.
    - `tracker_for(self, item_id: str, run_id: str) -> InMemoryRunTracker`
      — returns a tracker bound to that one record.
    - `list(self, item_id: str, *, limit: int, offset: int) -> list[dict]`
      — records for `item_id`, **most recently created first**, sliced
      `[offset:offset+limit]`. Returns `[]` for an unknown `item_id`
      (never raises).
  - `class InMemoryRunTracker` — implements `mark_running`/`mark_succeeded`/
    `mark_failed` per the Protocol, mutating the record it was bound to via
    `RunRegistry.tracker_for()`. Timestamps via
    `datetime.now(timezone.utc).isoformat()`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_pipeline_sidecar_tracker.py
# SPDX-License-Identifier: Apache-2.0
from app.pipelines.sidecar.tracker import RunRegistry


def test_create_returns_queued_record():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    records = registry.list("item-1", limit=10, offset=0)
    assert len(records) == 1
    assert records[0]["id"] == run_id
    assert records[0]["status"] == "queued"
    assert records[0]["startedAt"] is None
    assert records[0]["finishedAt"] is None
    assert records[0]["error"] is None
    assert records[0]["nodeStats"] == {}


def test_tracker_mark_running_sets_status_and_started_at():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_running()
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "running"
    assert record["startedAt"] is not None
    assert record["finishedAt"] is None


def test_tracker_mark_succeeded_sets_status_finished_at_and_stats():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_running()
    tracker.mark_succeeded({"n1": {"nodeId": "n1", "op": "reader.file", "rowCount": 2}})
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "succeeded"
    assert record["finishedAt"] is not None
    assert record["error"] is None
    assert record["nodeStats"] == {"n1": {"nodeId": "n1", "op": "reader.file", "rowCount": 2}}


def test_tracker_mark_failed_sets_status_and_error():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    tracker.mark_failed("boom")
    record = registry.list("item-1", limit=10, offset=0)[0]
    assert record["status"] == "failed"
    assert record["error"] == "boom"
    assert record["finishedAt"] is not None


def test_list_orders_most_recent_first_and_paginates():
    registry = RunRegistry()
    run_a = registry.create("item-1")
    run_b = registry.create("item-1")
    records = registry.list("item-1", limit=1, offset=0)
    assert [r["id"] for r in records] == [run_b]
    records = registry.list("item-1", limit=1, offset=1)
    assert [r["id"] for r in records] == [run_a]


def test_list_unknown_item_id_returns_empty_list():
    registry = RunRegistry()
    assert registry.list("no-such-item", limit=10, offset=0) == []


def test_list_isolates_records_by_item_id():
    registry = RunRegistry()
    registry.create("item-1")
    assert registry.list("item-2", limit=10, offset=0) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_tracker.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.pipelines.sidecar'`.

- [ ] **Step 3: Write the implementation**

```python
# core/app/pipelines/sidecar/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/pipelines/sidecar/tracker.py
# SPDX-License-Identifier: Apache-2.0
"""Suivi de run en mémoire (design desktop-etl §4) : implémente le
Protocol RunTracker (app.pipelines.jobs) sans Postgres, pour le sidecar
desktop. Un process, un utilisateur — un verrou global suffit, pas besoin
d'un verrou par item_id (design §1, non-but multi-utilisateur)."""

import threading
import uuid
from datetime import datetime, timezone


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, list[dict]] = {}

    def create(self, item_id: str) -> str:
        run_id = uuid.uuid4().hex
        record = {
            "id": run_id,
            "status": "queued",
            "startedAt": None,
            "finishedAt": None,
            "error": None,
            "nodeStats": {},
        }
        with self._lock:
            self._records.setdefault(item_id, []).insert(0, record)
        return run_id

    def tracker_for(self, item_id: str, run_id: str) -> "InMemoryRunTracker":
        return InMemoryRunTracker(self, item_id=item_id, run_id=run_id)

    def list(self, item_id: str, *, limit: int, offset: int) -> list[dict]:
        with self._lock:
            records = list(self._records.get(item_id, []))
        return records[offset : offset + limit]

    def _update(self, item_id: str, run_id: str, **fields: object) -> None:
        with self._lock:
            for record in self._records.get(item_id, []):
                if record["id"] == run_id:
                    record.update(fields)
                    return


class InMemoryRunTracker:
    def __init__(self, registry: RunRegistry, *, item_id: str, run_id: str) -> None:
        self._registry = registry
        self._item_id = item_id
        self._run_id = run_id

    def mark_running(self) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="running",
            startedAt=datetime.now(timezone.utc).isoformat(),
        )

    def mark_succeeded(self, node_stats: dict) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="succeeded",
            finishedAt=datetime.now(timezone.utc).isoformat(),
            nodeStats=node_stats,
        )

    def mark_failed(self, error: str) -> None:
        self._registry._update(
            self._item_id,
            self._run_id,
            status="failed",
            finishedAt=datetime.now(timezone.utc).isoformat(),
            error=error,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_tracker.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/sidecar/__init__.py core/app/pipelines/sidecar/tracker.py core/tests/test_pipeline_sidecar_tracker.py
git commit -m "feat(core): ajoute RunRegistry/InMemoryRunTracker du sidecar desktop-etl"
```

---

### Task 2: `PipelineStore` + `start_run()` (background execution)

**Files:**
- Create: `core/app/pipelines/sidecar/runner.py`
- Test: `core/tests/test_pipeline_sidecar_runner.py`

**Interfaces:**
- Consumes:
  - `RunRegistry`/`InMemoryRunTracker` from Task 1.
  - `app.pipelines.runtime.run_pipeline(session, *, payload, tenant_id, user, endpoint_url, access_key, secret_key, base_uri, s3_client=None, exports_bucket=None, qgis_worker_url="", qgis_worker_timeout_seconds=600, on_node_complete=None) -> list[NodeStat]`
    (`core/app/pipelines/runtime.py:1053-1068`) — call with
    `session=None, user=None, tenant_id="local"`.
  - `app.pipelines.runtime.NodeStat.to_dict() -> dict`
    (`core/app/pipelines/runtime.py:105-112`, `{"nodeId", "op", "rowCount"}`).
  - `app.pipelines.errors.PipelineRuntimeError`.
  - `app.configs.schemas.PipelinePayload`.
- Produces (for Task 3):
  - `class PipelineStore` with `set(self, item_id: str, payload: PipelinePayload) -> None`
    and `get(self, item_id: str) -> PipelinePayload | None`.
  - `def start_run(store: PipelineStore, registry: RunRegistry, item_id: str, *, base_uri: str) -> str | None`
    — returns the new `run_id`, or `None` if `store.get(item_id)` is `None`
    (caller turns that into a 404).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_pipeline_sidecar_runner.py
# SPDX-License-Identifier: Apache-2.0
import time

from app.configs.schemas import PipelinePayload
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry


def _write_geojson(tmp_path, name: str):
    path = tmp_path / name
    path.write_text(
        '{"type":"FeatureCollection","features":['
        '{"type":"Feature","properties":{"label":"a"},'
        '"geometry":{"type":"Point","coordinates":[1,2]}},'
        '{"type":"Feature","properties":{"label":"b"},'
        '"geometry":{"type":"Point","coordinates":[3,4]}}]}'
    )
    return str(path)


def _file_to_file_payload(in_path: str, out_path: str) -> PipelinePayload:
    return PipelinePayload.model_validate(
        {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.file", "params": {"path": in_path}},
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.file",
                    "params": {"path": out_path},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )


def _wait_until_finished(registry: RunRegistry, item_id: str, run_id: str, *, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = next(r for r in registry.list(item_id, limit=10, offset=0) if r["id"] == run_id)
        if record["status"] in ("succeeded", "failed"):
            return record
        time.sleep(0.05)
    raise AssertionError("run did not finish within timeout")


def test_start_run_returns_none_when_no_payload_stored():
    store = PipelineStore()
    registry = RunRegistry()
    assert start_run(store, registry, "no-such-item", base_uri="/tmp") is None


def test_start_run_executes_pipeline_and_marks_succeeded(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")
    store = PipelineStore()
    registry = RunRegistry()
    store.set("item-1", _file_to_file_payload(in_path, out_path))

    run_id = start_run(store, registry, "item-1", base_uri=str(tmp_path))
    assert run_id is not None

    record = _wait_until_finished(registry, "item-1", run_id)
    assert record["status"] == "succeeded"
    assert set(record["nodeStats"]) == {"r1", "w1"}
    import os

    assert os.path.exists(out_path)


def test_start_run_marks_failed_on_bad_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    store = PipelineStore()
    registry = RunRegistry()
    store.set("item-1", _file_to_file_payload(str(tmp_path / "missing.geojson"), str(tmp_path / "out.gpkg")))

    run_id = start_run(store, registry, "item-1", base_uri=str(tmp_path))
    record = _wait_until_finished(registry, "item-1", run_id)
    assert record["status"] == "failed"
    assert record["error"]


def test_pipeline_store_get_returns_none_for_unknown_item():
    store = PipelineStore()
    assert store.get("no-such-item") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_runner.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.pipelines.sidecar.runner'`.

- [ ] **Step 3: Write the implementation**

```python
# core/app/pipelines/sidecar/runner.py
# SPDX-License-Identifier: Apache-2.0
"""Exécution d'un pipeline sans Postgres/procrastinate (design desktop-etl
§4) : réutilise app.pipelines.runtime.run_pipeline() tel quel (session=None
— sûr uniquement pour reader.file/transform/writer.file, cf. Global
Constraints du plan), dans un thread daemon, avec le RunTracker en mémoire
de sidecar.tracker. Ce n'est PAS run_pipeline_task (jobs.py) : ce dernier
est câblé en dur à Postgres/S3/notifications (chargement de la config,
utilisateur, tracker), rien de tout cela n'a de sens ici — seul l'appel au
moteur (runtime.run_pipeline) est partagé."""

import threading

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.sidecar.tracker import RunRegistry


class PipelineStore:
    def __init__(self) -> None:
        self._payloads: dict[str, PipelinePayload] = {}

    def set(self, item_id: str, payload: PipelinePayload) -> None:
        self._payloads[item_id] = payload

    def get(self, item_id: str) -> PipelinePayload | None:
        return self._payloads.get(item_id)


def _execute(registry: RunRegistry, item_id: str, run_id: str, payload: PipelinePayload, base_uri: str) -> None:
    tracker = registry.tracker_for(item_id, run_id)
    tracker.mark_running()
    try:
        stats = runtime.run_pipeline(
            None,
            payload=payload,
            tenant_id="local",
            user=None,
            endpoint_url="",
            access_key="",
            secret_key="",
            base_uri=base_uri,
        )
    except (PipelineRuntimeError, ValueError) as exc:
        tracker.mark_failed(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — même patron que jobs.py:run_pipeline_task
        tracker.mark_failed(f"erreur interne : {exc}")
        return
    tracker.mark_succeeded({s.nodeId: s.to_dict() for s in stats})


def start_run(store: PipelineStore, registry: RunRegistry, item_id: str, *, base_uri: str) -> str | None:
    payload = store.get(item_id)
    if payload is None:
        return None
    run_id = registry.create(item_id)
    thread = threading.Thread(
        target=_execute, args=(registry, item_id, run_id, payload, base_uri), daemon=True
    )
    thread.start()
    return run_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_runner.py -v`
Expected: 4 passed. (If `/tmp/pytest-of-<user>` ownership fails, add
`--basetemp=<scratch dir>`, per Global Constraints.)

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/sidecar/runner.py core/tests/test_pipeline_sidecar_runner.py
git commit -m "feat(core): ajoute PipelineStore/start_run du sidecar desktop-etl"
```

---

### Task 3: FastAPI app (`create_sidecar_app`)

**Files:**
- Create: `core/app/pipelines/sidecar/app.py`
- Test: `core/tests/test_pipeline_sidecar_app.py`

**Interfaces:**
- Consumes:
  - `PipelineStore`/`start_run` (Task 2), `RunRegistry` (Task 1).
  - `app.pipelines.ops.contracts.ops_catalog() -> dict[str, dict]`
    (`core/app/pipelines/ops/contracts.py:424-438`).
  - `app.pipelines.runtime.preview_pipeline(*, session, payload, tenant_id, user, up_to, endpoint_url, access_key, secret_key, base_uri, limit=50, qgis_worker_url="", qgis_worker_timeout_seconds=600) -> list[dict]`
    (`core/app/pipelines/runtime.py:712-726`) — call with
    `session=None, user=None, tenant_id="local"`.
  - `app.configs.schemas.PipelinePayload`.
- Produces (for Task 4 and for the future Phase G `ItemClient`):
  - `def create_sidecar_app(*, base_uri: str) -> fastapi.FastAPI` exposing
    the 5 routes of the roadmap's §3.1 table verbatim.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_pipeline_sidecar_app.py
# SPDX-License-Identifier: Apache-2.0
import time

import httpx
import pytest

from app.pipelines.sidecar.app import create_sidecar_app


def _write_geojson(tmp_path, name: str):
    path = tmp_path / name
    path.write_text(
        '{"type":"FeatureCollection","features":['
        '{"type":"Feature","properties":{"label":"a"},'
        '"geometry":{"type":"Point","coordinates":[1,2]}},'
        '{"type":"Feature","properties":{"label":"b"},'
        '"geometry":{"type":"Point","coordinates":[3,4]}}]}'
    )
    return str(path)


def _payload_dict(in_path: str, out_path: str) -> dict:
    return {
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.file", "params": {"path": in_path}},
            {"id": "w1", "kind": "writer", "op": "writer.file", "params": {"path": out_path}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    }


@pytest.fixture
def client(tmp_path):
    app = create_sidecar_app(base_uri=str(tmp_path))
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://sidecar") as c:
        yield c


def test_get_ops_includes_reader_file_and_writer_file(client):
    res = client.get("/pipelines/ops")
    assert res.status_code == 200
    catalog = res.json()
    assert "reader.file" in catalog
    assert "writer.file" in catalog
    assert catalog["reader.file"]["kind"] == "reader"


def test_run_without_stored_payload_returns_404(client):
    res = client.post("/pipelines/no-such-item/run")
    assert res.status_code == 404


def test_put_then_run_then_poll_runs_until_succeeded(client, tmp_path):
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")

    put_res = client.put("/pipelines/item-1", json=_payload_dict(in_path, out_path))
    assert put_res.status_code == 204

    run_res = client.post("/pipelines/item-1/run")
    assert run_res.status_code == 202
    run_id = run_res.json()["runId"]
    assert isinstance(run_id, str) and run_id

    deadline = time.monotonic() + 10.0
    latest = None
    while time.monotonic() < deadline:
        runs_res = client.get("/pipelines/item-1/runs")
        assert runs_res.status_code == 200
        runs = runs_res.json()
        assert runs[0]["id"] == run_id
        if runs[0]["status"] in ("succeeded", "failed"):
            latest = runs[0]
            break
        time.sleep(0.05)
    assert latest is not None
    assert latest["status"] == "succeeded"
    assert set(latest["nodeStats"]) == {"r1", "w1"}


def test_runs_pagination_params_are_accepted(client):
    res = client.get("/pipelines/item-1/runs?limit=5&offset=0")
    assert res.status_code == 200
    assert res.json() == []


def test_preview_without_stored_payload_returns_404(client):
    res = client.post("/pipelines/no-such-item/preview?upTo=r1")
    assert res.status_code == 404


def test_put_then_preview_returns_rows(client, tmp_path):
    in_path = _write_geojson(tmp_path, "in.geojson")
    out_path = str(tmp_path / "out.gpkg")
    client.put("/pipelines/item-2", json=_payload_dict(in_path, out_path))

    res = client.post("/pipelines/item-2/preview?upTo=r1")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert {row["label"] for row in rows} == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_app.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.pipelines.sidecar.app'`.

- [ ] **Step 3: Write the implementation**

```python
# core/app/pipelines/sidecar/app.py
# SPDX-License-Identifier: Apache-2.0
"""API loopback du sidecar desktop-etl (design §4, roadmap §3.1) : rejoue
la forme des routes cœur (app.pipelines.routes) sans Postgres/auth/tenant —
mono-utilisateur, mono-process, 127.0.0.1 uniquement (jamais exposé sur
0.0.0.0, cf. Phase E du plan et l'entrypoint de la Tâche 4)."""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import ops_catalog
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry


def create_sidecar_app(*, base_uri: str) -> FastAPI:
    # Actif par défaut côté sidecar desktop, jamais côté cœur (design §3) —
    # posé ici, pas supposé déjà présent dans l'environnement appelant.
    os.environ["CORE_PIPELINE_FILE_IO_ENABLED"] = "true"

    app = FastAPI()
    store = PipelineStore()
    registry = RunRegistry()

    @app.put("/pipelines/{item_id}", status_code=204)
    def put_pipeline(item_id: str, payload: PipelinePayload) -> Response:
        store.set(item_id, payload)
        return Response(status_code=204)

    @app.get("/pipelines/ops")
    def get_ops() -> dict:
        return ops_catalog()

    @app.post("/pipelines/{item_id}/run", status_code=202)
    def run_pipeline_route(item_id: str) -> dict:
        run_id = start_run(store, registry, item_id, base_uri=base_uri)
        if run_id is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        return {"runId": run_id}

    @app.get("/pipelines/{item_id}/runs")
    def get_runs(item_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        return registry.list(item_id, limit=limit, offset=offset)

    @app.post("/pipelines/{item_id}/preview")
    def preview_pipeline_route(item_id: str, upTo: str = Query(...)) -> list[dict]:
        payload = store.get(item_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        try:
            return runtime.preview_pipeline(
                session=None,
                payload=payload,
                tenant_id="local",
                user=None,
                up_to=upTo,
                endpoint_url="",
                access_key="",
                secret_key="",
                base_uri=base_uri,
            )
        except PipelineRuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_app.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/sidecar/app.py core/tests/test_pipeline_sidecar_app.py
git commit -m "feat(core): ajoute l'app FastAPI loopback du sidecar desktop-etl"
```

---

### Task 4: Entrypoint réel (`core/scripts/pipeline_sidecar.py`)

**Files:**
- Create: `core/scripts/pipeline_sidecar.py`
- Test: `core/tests/test_pipeline_sidecar_entrypoint.py`

**Interfaces:**
- Consumes: `create_sidecar_app` (Task 3).
- Produces: a `main(base_uri: str | None = None) -> int` function the
  Phase G Tauri shell will eventually spawn as a frozen binary
  (`core/scripts/pipeline_sidecar_spike.py` remains untouched — it is the
  D1 freeze-only spike script, not superseded by this file; a real
  PyInstaller recipe for this new entrypoint is Phase F's job, not this
  task's).

**Design decision for this task, verify against the installed uvicorn
before writing code (`uv run python -c "import uvicorn; help(uvicorn.Server.serve)"`),
per CLAUDE.md piège #3 — do not assume the signature below is correct
without having run that check first:** bind a plain `socket.socket()` to
`("127.0.0.1", 0)` to learn the OS-assigned ephemeral port *before*
starting to serve, print `PORT=<n>` on stdout immediately (this is the
handshake line a parent Tauri process reads in Phase G), then hand that
already-bound socket to `uvicorn.Server(...).run(sockets=[sock])` — this
avoids needing a `port=0`-then-discover-later dance, and works identically
on Windows (no fd-passing, just the live Python socket object in the same
process).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_pipeline_sidecar_entrypoint.py
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
import sys
import time

import httpx


def test_entrypoint_prints_port_and_serves_ops(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "scripts/pipeline_sidecar.py", "--base-uri", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=".",
    )
    try:
        first_line = proc.stdout.readline()
        match = re.match(r"PORT=(\d+)\n", first_line)
        assert match, f"unexpected first line: {first_line!r}, stderr={proc.stderr.read()}"
        port = int(match.group(1))

        deadline = time.monotonic() + 5.0
        last_exc = None
        while time.monotonic() < deadline:
            try:
                res = httpx.get(f"http://127.0.0.1:{port}/pipelines/ops", timeout=1.0)
                assert res.status_code == 200
                assert "reader.file" in res.json()
                return
            except httpx.TransportError as exc:
                last_exc = exc
                time.sleep(0.1)
        raise AssertionError(f"sidecar never became reachable: {last_exc}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: FAIL — `scripts/pipeline_sidecar.py` does not exist yet.

- [ ] **Step 3: Write the implementation**

First, run `uv run python -c "import uvicorn; print(uvicorn.Config.__init__.__doc__); print(uvicorn.Server.run.__doc__)"`
and confirm `Server.run(sockets: list[socket.socket] | None = None)` accepts
pre-bound sockets (adjust the code below if the installed 0.49.0 API
differs from what this step assumes — do not skip this check).

```python
# core/scripts/pipeline_sidecar.py
# SPDX-License-Identifier: Apache-2.0
"""Point d'entrée réel du sidecar desktop-etl (Phase E, design §2/§4).
Diffère de scripts/pipeline_sidecar_spike.py (spike de gel PyInstaller
D1, jamais mis à jour pour rester une preuve isolée) : ce script sert
l'API loopback complète (app.pipelines.sidecar.app), pas un seul appel de
contrôle. Gelé en binaire PyInstaller en Phase F/G, pas ici.

Handshake avec le futur process parent (Tauri, Phase G) : la toute
première ligne de stdout est "PORT=<n>\\n", où <n> est le port TCP
127.0.0.1 effectivement choisi par l'OS — même patron que `gh auth
login`/`aws sso login` pour un listener loopback (design §5)."""

import argparse
import socket
import sys
import tempfile

import uvicorn

from app.pipelines.sidecar.app import create_sidecar_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-uri", default=None)
    args = parser.parse_args(argv)
    base_uri = args.base_uri or tempfile.mkdtemp(prefix="geostudio-sidecar-")

    app = create_sidecar_app(base_uri=base_uri)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    print(f"PORT={port}", flush=True)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: 1 passed.

If the `uvicorn.Server.run(sockets=...)` call fails or blocks in a way
that keeps the subprocess from ever printing past the port line, this is
exactly the kind of third-party-API mismatch CLAUDE.md piège #3 warns
about — inspect the actual installed `uvicorn` source
(`uv run python -c "import uvicorn, inspect; print(inspect.getsource(uvicorn.Server.run))"`)
rather than retrying the same call with minor tweaks.

- [ ] **Step 5: Commit**

```bash
git add core/scripts/pipeline_sidecar.py core/tests/test_pipeline_sidecar_entrypoint.py
git commit -m "feat(core): ajoute l'entrypoint réel du sidecar desktop-etl (handshake port)"
```

---

### Task 5: Vérification bout-en-bout + suite complète + portes de qualité

**Files:** none created; verification only, matching every prior
desktop-etl plan's closing task.

**Interfaces:** none (verification task).

- [ ] **Step 1: Run the new sidecar tests together**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_tracker.py tests/test_pipeline_sidecar_runner.py tests/test_pipeline_sidecar_app.py tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: all passed, 0 failed.

- [ ] **Step 2: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: 0 failed (same `postgis`/`qgis` skip counts as before this
plan — do not attribute a change in skip count to this plan's code
without checking `CORE_TEST_DATABASE_URL`/`CORE_TEST_QGIS_WORKER_URL`
first, per CLAUDE.md's documented pitfalls).

- [ ] **Step 3: Run the quality gates**

Run:
```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```
Expected: all clean, coverage ≥ 85 (regenerate `coverage.xml` first with
`uv run pytest --cov=app --cov-report=xml` if the check script needs it —
check the existing CI invocation in `.github/workflows/ci.yml`'s `core`
job for the exact flags this repo uses, rather than guessing new ones).

- [ ] **Step 4: Update the feature inventory**

This phase adds no new *externally reachable* surface (no new REST route
under `/v1/`, no new MCP tool, no new shell route) — the sidecar's routes
are not mounted into `core/app/main.py`'s `v1_router` and are unreachable
from the real GeoStudio core/shell. Confirm this by grepping
`core/app/main.py` for `sidecar` (expect zero hits) before skipping the
`docs/revue/inventaire-fonctionnalites.jsonl` update that CLAUDE.md
otherwise requires at the close of a chantier that ships a new surface.

- [ ] **Step 5: Update the roadmap doc's status line for Phase E**

Edit `docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md`
§4 "Phase E" to note it is closed, with the commit range, mirroring how
every prior desktop-etl phase is recorded in
`docs/superpowers/2026-08-27-historique-execution-continu.md` (append an
entry there too, per CLAUDE.md's "À la clôture d'un SP" rule — this is a
sub-phase of the still-open desktop-etl chantier, not a full SP, so use
judgement on whether a dedicated entry or a note under the existing
desktop-etl entries fits better; do not add a line to `CLAUDE.md`'s
`### Livré` yet — that is reserved for when the whole desktop-etl product
ships, per the size guard-rail already in place there).

- [ ] **Step 6: Commit the plan document itself**

```bash
git add docs/superpowers/plans/2026-09-18-desktop-etl-sidecar-engine.md docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md
git commit -m "docs(superpowers): versionne le plan + la feuille de route du sidecar desktop-etl"
```

---

## Self-Review Notes (already applied above)

- **Spec coverage**: every row of the roadmap's §3.1 HTTP contract table
  has a corresponding route in Task 3; the `RunTracker`/`PipelineStore`
  seams from the roadmap's §1 are Tasks 1/2; the port-handshake need from
  Phase G is Task 4.
- **No placeholders**: every step has real, complete code — the one
  explicitly flagged uncertainty (Task 4's `uvicorn.Server.run(sockets=...)`
  signature) is called out as "verify before writing", not silently
  assumed, per CLAUDE.md piège #3, and comes with a concrete fallback
  instruction (read the installed source) rather than a vague "handle
  errors".
- **Type consistency**: `RunRegistry.list()` return shape
  (`id`/`status`/`startedAt`/`finishedAt`/`error`/`nodeStats`) is used
  identically in Tasks 1, 2's tests (via the registry), and 3's route
  (returned as-is, no reshaping) — matches `RunStatus`
  (`core/app/pipelines/routes.py:33-43`) and TypeScript `PipelineRun`
  (`shell/src/api/types.ts:1123-1130`) field-for-field.
