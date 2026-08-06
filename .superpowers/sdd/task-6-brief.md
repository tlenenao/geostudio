## Task 6: `routes.py` + `jobs.py` — env var wiring + algorithm catalogue resource

**Files:**
- Modify: `core/app/pipelines/routes.py`
- Modify: `core/app/pipelines/jobs.py`
- Test: `core/tests/test_pipeline_routes.py`

**Interfaces:**
- Consumes: `QGIS_ALGORITHMS` (Task 1), `run_pipeline`/`preview_pipeline`'s
  new kwargs (Task 5).
- Produces: `GET /pipelines/ops/qgis-algorithms` (public REST resource,
  returns the full allowlist + schemas). `QGIS_WORKER_URL`/
  `QGIS_WORKER_TIMEOUT_SECONDS` env vars now read and threaded through both
  the run job and the preview route.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_routes.py`:

```python
def test_get_qgis_algorithms_returns_full_allowlist(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops/qgis-algorithms")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 50
    assert "native:centroids" in body
    assert "ALL_PARTS" in body["native:centroids"]["parameters"]


def test_get_qgis_algorithms_absent_when_etl_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/pipelines/ops/qgis-algorithms").status_code == 404
```

No new fixture: this file uses a local `_make_app(monkeypatch, *,
etl_enabled)` helper (not a shared pytest fixture) that builds a
`TestClient` with `CORE_ETL_ENABLED` set via `monkeypatch.setenv` — reused
here exactly as `test_get_pipelines_ops_returns_all_eight` already does.
The new route is registered on the same `router` as the rest of
`app.pipelines.routes`, so it inherits the existing `CORE_ETL_ENABLED`
gating (whatever mounts/unmounts the router based on that env var already
covers it) — the second test above locks that in explicitly rather than
assuming it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -k qgis_algorithms -v`
Expected: FAIL — 404, route doesn't exist yet.

- [ ] **Step 3: Add the route**

Modify `core/app/pipelines/routes.py` — add the import:

```python
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
```

Add right after the existing `GET /pipelines/ops` route:

```python
@router.get("/pipelines/ops/qgis-algorithms")
def get_qgis_algorithms() -> dict:
    return QGIS_ALGORITHMS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -k qgis_algorithms -v`
Expected: PASS.

- [ ] **Step 5: Thread the env vars through `preview_pipeline_route`**

Modify `core/app/pipelines/routes.py`'s `preview_pipeline_route`:

```python
        return preview_pipeline(
            session=session, payload=config.config.pipeline, tenant_id=user.tenant_id, user=user,
            up_to=upTo, endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""), secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
            qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
        )
```

- [ ] **Step 6: Thread the env vars through `run_pipeline_task`**

Modify `core/app/pipelines/jobs.py`'s `run_pipeline_task`:

```python
            stats = run_pipeline(
                session, payload=payload, tenant_id=tenant_id, user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
                qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
                qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
            )
```

- [ ] **Step 7: Run the full pipelines route/jobs test files**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py tests/test_pipeline_jobs.py -v`
Expected: all pass, no regression (existing tests don't set
`QGIS_WORKER_URL`, so `run_pipeline`/`preview_pipeline` receive `""` — the
same as their new default, no behavior change for pipelines without a
`transform.qgis` node).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/routes.py core/app/pipelines/jobs.py core/tests/test_pipeline_routes.py
git commit -m "feat(core): wire QGIS_WORKER_URL env + publish the algorithm catalogue resource"
```

---

