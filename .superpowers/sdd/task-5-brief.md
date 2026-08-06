## Task 5: `runtime.py` — dispatch `transform.qgis`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `TransformQgisParams` (Task 2), `qgis_worker_url`/
  `qgis_scratch_dir` fixtures (Task 4), `httpx` (already a dependency).
- Produces: `run_pipeline(...)` and `preview_pipeline(...)` gain two new
  keyword params, `qgis_worker_url: str = ""` and
  `qgis_worker_timeout_seconds: int = 600` — consumed by Task 6
  (`routes.py`/`jobs.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py`:

```python
def test_execute_qgis_transform_raises_clean_error_without_worker_url(tmp_path, monkeypatch):
    """No QGIS_WORKER_URL configured (profile 'etl' not enabled) must fail
    the run cleanly, never crash on a connection error."""
    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: _table_info_for(cid))
    _write_partition(tmp_path, rows=[_row(1, "Nord", 1, x=2.35, y=48.85)])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}],
    })
    with pytest.raises(runtime.PipelineRuntimeError, match="QGIS_WORKER_URL"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k qgis_transform_raises -v`
Expected: FAIL — `transform.qgis` isn't dispatched at all yet,
`compiler.compile_transform_sql` raises `ValueError("'transform.qgis' is
not a transform op")`, which is unhandled (propagates as a raw
`ValueError`, not `PipelineRuntimeError` with the expected message).

- [ ] **Step 3: Implement the dispatch branch**

Modify `core/app/pipelines/runtime.py` — extend imports:

```python
import os
import uuid

import httpx
```

(add `os`, `uuid`, `httpx` to the existing `import csv / import io / import
json` block, alphabetically: `import csv`, `import io`, `import json`,
`import os`, `import uuid`, blank line, `import duckdb`, `import httpx`,
blank line, `from sqlalchemy.orm import Session`)

Add `TransformQgisParams` to the existing `from app.pipelines.ops.schemas
import (...)` block.

Add a new helper, right before `_execute_transform_chain`:

```python
def _execute_qgis_transform(
    conn, node: PipelineNode, *, input_view: str, input_srid: int,
    qgis_worker_url: str, qgis_worker_timeout_seconds: int, scratch_run_id: str,
) -> None:
    if not qgis_worker_url:
        raise PipelineRuntimeError(
            "transform.qgis requires QGIS_WORKER_URL to be configured (profile 'etl')"
        )
    p = TransformQgisParams.model_validate(node.params)
    scratch_dir = f"/scratch/{scratch_run_id}/{node.id}"
    in_path = f"{scratch_dir}/in.gpkg"
    out_path = f"{scratch_dir}/out.gpkg"
    os.makedirs(scratch_dir, exist_ok=True)
    # SRS explicite obligatoire : sans elle, DuckDB écrit "Undefined
    # geographic SRS" (vérifié en design §2) et qgis_process interprète les
    # géométries dans un CRS inconnu.
    conn.execute(
        f"COPY (SELECT * FROM {_qi(input_view)}) TO '{in_path}' "
        f"WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:{input_srid}')"
    )
    try:
        response = httpx.post(
            f"{qgis_worker_url}/run",
            json={
                "algorithmId": p.algorithmId,
                "inputs": {**p.params, "INPUT": in_path, "OUTPUT": out_path},
            },
            timeout=qgis_worker_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise PipelineRuntimeError(
            f"transform.qgis ({p.algorithmId}) : timeout après {qgis_worker_timeout_seconds}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise PipelineRuntimeError(
            f"transform.qgis ({p.algorithmId}) : échec de connexion au sidecar qgis-worker : {exc}"
        ) from exc
    if response.status_code != 200:
        detail = response.json().get("error", response.text)
        raise PipelineRuntimeError(f"transform.qgis ({p.algorithmId}) : {detail}")
    view_name = f"node_{node.id}"
    conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM ST_Read('{out_path}')")
    # Best-effort : ne bloque jamais le run si le nettoyage échoue (design
    # §12, risque accepté — un scratch non nettoyé après un CRASH, pas après
    # un succès, reste un problème d'exploitation mineur).
    import shutil
    shutil.rmtree(scratch_dir, ignore_errors=True)
```

Modify `_execute_transform_chain`'s signature and body:

```python
def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str],
    srid_by_node: dict[str, int], join_srid_by_node: dict[str, int],
    *, stop_at: str | None = None, qgis_worker_url: str = "",
    qgis_worker_timeout_seconds: int = 600,
) -> list["NodeStat"]:
    stats: list[NodeStat] = []
    scratch_run_id = uuid.uuid4().hex
    for node in ordered:
        if node.kind == "reader":
            stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_by_node[node.id])))
            if stop_at == node.id:
                return stats
            continue
        if node.kind != "transform":
            break  # writer nodes are handled by the caller, not here
        pred_id = compiler.predecessor_id(node.id, edges)
        assert pred_id is not None
        input_view = view_by_node[pred_id]
        input_srid = srid_by_node[pred_id]
        join_view = f"node_{node.id}__join" if node.op in _JOIN_PARAM_MODELS else None
        join_srid = join_srid_by_node.get(node.id)
        _validate_node_exprs(conn, node)
        try:
            output_srid = compiler.transform_output_srid(
                node.op, node.params, input_srid=input_srid, join_srid=join_srid,
            )
        except ValueError as exc:
            raise PipelineRuntimeError(str(exc)) from exc
        view_name = f"node_{node.id}"
        if node.op == "transform.qgis":
            _execute_qgis_transform(
                conn, node, input_view=input_view, input_srid=input_srid,
                qgis_worker_url=qgis_worker_url,
                qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
                scratch_run_id=scratch_run_id,
            )
        else:
            sql = compiler.compile_transform_sql(
                node.op, node.params, input_view=input_view, join_view=join_view, input_srid=input_srid,
            )
            conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = output_srid
        stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_name)))
        if stop_at == node.id:
            return stats
    return stats
```

Modify `preview_pipeline`'s signature and its call to
`_execute_transform_chain`:

```python
def preview_pipeline(
    *, session: Session | None, payload: PipelinePayload, tenant_id: str, user: User | None,
    up_to: str, endpoint_url: str, access_key: str, secret_key: str, base_uri: str, limit: int = 50,
    qgis_worker_url: str = "", qgis_worker_timeout_seconds: int = 600,
) -> list[dict]:
```

```python
        _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
            stop_at=up_to, qgis_worker_url=qgis_worker_url,
            qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
        )
```

Modify `run_pipeline`'s signature and its call to
`_execute_transform_chain`:

```python
def run_pipeline(
    session: Session, *, payload: PipelinePayload, tenant_id: str, user: User,
    endpoint_url: str, access_key: str, secret_key: str, base_uri: str,
    s3_client=None, exports_bucket: str | None = None,
    qgis_worker_url: str = "", qgis_worker_timeout_seconds: int = 600,
) -> list[NodeStat]:
```

```python
        stats = _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
            qgis_worker_url=qgis_worker_url, qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k qgis_transform_raises -v`
Expected: PASS — `PipelineRuntimeError` raised with "QGIS_WORKER_URL" in
the message, before any file/network I/O is attempted.

- [ ] **Step 5: Write the real end-to-end dispatch test (needs the sidecar)**

Append to `core/tests/test_pipeline_runtime.py`:

```python
@pytest.mark.qgis
def test_execute_qgis_transform_computes_centroids(tmp_path, monkeypatch, qgis_worker_url):
    """reader.collection (2 polygons) -> transform.qgis(native:centroids) ->
    preview: real sidecar round-trip, real DuckDB COPY/ST_Read (design §6).
    Requires /scratch to be the SAME directory the qgis-worker container in
    Task 4 Step 5 has bind-mounted at /scratch — this test writes via
    DuckDB's COPY (inside this Python process, on the host), the sidecar
    reads the identical path from inside its container."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    polygons_info = dataclasses.replace(
        TABLE_INFO, table_name="polygons", geometry_type="Polygon",
        columns=[ColumnInfo(name="region", type="string", required=True)],
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: polygons_info)

    _write_partition(tmp_path, collection_id="polygons", rows=[
        {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])},
        {"id": 2, "region": "b", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(10, 10), (10, 12), (12, 12), (12, 10)])},
    ])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}],
    })
    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
    )
    assert len(rows) == 2
    centroids = sorted(
        (row["geometry"]["coordinates"][0], row["geometry"]["coordinates"][1]) for row in rows
    )
    assert centroids == [(1.0, 1.0), (11.0, 11.0)]
```

Note: this test needs `/scratch` writable by the host process running
pytest (same one-time `sudo mkdir -p /scratch && sudo chown "$(whoami)"
/scratch` from Task 4 Step 5) — the container from Task 4 must be running
with `-v /scratch:/scratch` for the paths to match on both sides.

- [ ] **Step 6: Run test to verify it fails without setup, passes with it**

Run (no sidecar running): `cd core && uv run pytest tests/test_pipeline_runtime.py -k computes_centroids -v`
Expected: 1 skipped (`CORE_TEST_QGIS_WORKER_URL non défini`).

Run (with the Task 4 Step 5/9 setup — container running, env vars set):
```bash
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
cd core && uv run pytest tests/test_pipeline_runtime.py -k computes_centroids -v
```
Expected: 1 passed — centroids `(1.0, 1.0)` and `(11.0, 11.0)` match the
two synthetic squares' actual centers exactly (deterministic geometry, no
floating-point tolerance needed).

- [ ] **Step 7: Run the full test file to check for regressions**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: all pass (postgis/qgis-marked tests skipped if those env vars
aren't set, everything else passes unconditionally).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py
git commit -m "feat(core): runtime dispatch for transform.qgis via the qgis-worker sidecar"
```

---

