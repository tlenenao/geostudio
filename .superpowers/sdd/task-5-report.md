# Task 5 report — `runtime.py` dispatch for `transform.qgis`

## Status: DONE

Commit: `f55bf5f` — `feat(core): runtime dispatch for transform.qgis via the qgis-worker sidecar`

## What was implemented

`core/app/pipelines/runtime.py`:
- Extended imports: `os`, `uuid` (alphabetical with `csv`/`io`/`json`), `httpx`
  (alongside `duckdb`), `TransformQgisParams` added to the
  `app.pipelines.ops.schemas` import block.
- New helper `_execute_qgis_transform(conn, node, *, input_view, input_srid,
  qgis_worker_url, qgis_worker_timeout_seconds, scratch_run_id)` placed right
  before `_execute_transform_chain`:
  - Raises `PipelineRuntimeError` immediately (no I/O) if `qgis_worker_url`
    is falsy — this is the "profile 'etl' not enabled" clean-failure path.
  - Validates `node.params` via `TransformQgisParams`.
  - Writes the upstream DuckDB relation to
    `/scratch/{scratch_run_id}/{node.id}/in.gpkg` via `COPY ... WITH (FORMAT
    GDAL, DRIVER 'GPKG', SRS 'EPSG:{input_srid}')` — the explicit SRS is
    mandatory (DuckDB otherwise writes "Undefined geographic SRS").
  - POSTs to `{qgis_worker_url}/run` with `{algorithmId, inputs: {**params,
    INPUT, OUTPUT}}`, catching `httpx.TimeoutException` and `httpx.HTTPError`
    into `PipelineRuntimeError` with a French message; non-200 responses
    likewise raise with the sidecar's `error` detail.
  - Reloads the result via `CREATE TEMP TABLE node_{id} AS SELECT * FROM
    ST_Read('{out_path}')`.
  - Best-effort `shutil.rmtree(scratch_dir, ignore_errors=True)` cleanup.
- `_execute_transform_chain`: gained `qgis_worker_url: str = ""` and
  `qgis_worker_timeout_seconds: int = 600` keyword params, a per-call
  `scratch_run_id = uuid.uuid4().hex`, and a dispatch branch — when
  `node.op == "transform.qgis"`, calls `_execute_qgis_transform` instead of
  `compiler.compile_transform_sql` + `CREATE TEMP VIEW`. All other ops go
  through the untouched `compiler.compile_transform_sql` path (same `if/else`
  structure, no behavior change).
- `preview_pipeline` and `run_pipeline`: both gained the same two keyword
  params, threaded through to their `_execute_transform_chain` call.

`core/tests/test_pipeline_runtime.py`: two new tests appended, matching the
brief's Step 1 and Step 5 code, with one necessary correction (see below).

## Deviation from the brief (and why)

The brief's Step 1/Step 5 test payloads only had a `reader` + `transform`
node, no `writer` node. Running Step 2 as literally specified failed with
`pydantic_core.ValidationError: pipeline requires at least one writer node`
— a `PipelinePayload` model validator (`app/configs/schemas.py:207`,
pre-existing, unrelated to this task) requires at least one writer node in
every payload, confirmed by every other test in this file (e.g.
`test_preview_h3_aggregate_requires_4326_reproject_first`, which also
targets `up_to="t1"` on an earlier node but still declares a `w1` writer.export
node + edge). I added the same minimal `writer.export` node + edge to both
new tests so the payload validates and the test actually exercises the
dispatch logic being tested, rather than failing on an unrelated schema
requirement. No other change from the brief's specified code.

## TDD evidence

**RED** (Step 2, before implementation) — confirms the brief's exact claim,
raw `ValueError`, not `PipelineRuntimeError`:

```
>       raise ValueError(f"'{op}' is not a transform op")
E       ValueError: 'transform.qgis' is not a transform op
app/pipelines/compiler.py:160: ValueError
FAILED tests/test_pipeline_runtime.py::test_execute_qgis_transform_raises_clean_error_without_worker_url
1 failed, 16 deselected in 0.85s
```

**GREEN** (Step 4, after implementation):

```
tests/test_pipeline_runtime.py::test_execute_qgis_transform_raises_clean_error_without_worker_url PASSED [100%]
1 passed, 16 deselected in 0.77s
```

(`pytest.raises(runtime.PipelineRuntimeError, match="QGIS_WORKER_URL")` —
clean failure before any file/network I/O, as required.)

## Sidecar-dependent test (Step 5/6)

`test_execute_qgis_transform_computes_centroids` (`@pytest.mark.qgis`) was
written exactly per the brief — real reader (2 polygons) -> `transform.qgis`
(`native:centroids`) -> `preview_pipeline` round-trip through a real
`qgis-worker` sidecar. It uses the `qgis_worker_url` fixture from
`tests/conftest.py` (added in Task 4), which skips with
`CORE_TEST_QGIS_WORKER_URL non défini` when unset.

Per this session's infra constraint (no writable `/scratch`, no running
sidecar container), only the "no sidecar" half of Step 6 was run:

```
tests/test_pipeline_runtime.py::test_execute_qgis_transform_computes_centroids SKIPPED [100%]
1 skipped, 16 deselected in 0.63s
```

Clean skip, not a failure or error. The "with sidecar" half (env var set,
container running with `-v /scratch:/scratch`) was intentionally NOT
attempted, per explicit instructions — it remains unverified until a future
session with `/scratch` access. The test code is correct-looking (payload,
fixtures, assertions all match the brief) but its actual end-to-end
correctness against a real `qgis_process native:centroids` call is unproven
by this session.

## Full test file (Step 7)

```
tests/test_pipeline_runtime.py::test_preview_filter_and_derive PASSED
tests/test_pipeline_runtime.py::test_preview_rejects_writer_node_as_up_to PASSED
tests/test_pipeline_runtime.py::test_preview_pipeline_serializes_geometry PASSED
tests/test_pipeline_runtime.py::test_write_export_geojson_serializes_geometry PASSED
tests/test_pipeline_runtime.py::test_write_export_csv_geometry_as_geojson_string PASSED
tests/test_pipeline_runtime.py::test_run_pipeline_writes_into_target_collection SKIPPED
tests/test_pipeline_runtime.py::test_preview_buffer_then_reproject PASSED
tests/test_pipeline_runtime.py::test_preview_h3_aggregate_requires_4326_reproject_first PASSED
tests/test_pipeline_runtime.py::test_preview_count_within_across_two_readers PASSED
tests/test_pipeline_runtime.py::test_preview_intersection_crs_mismatch_raises PASSED
tests/test_pipeline_runtime.py::test_h3_aggregate_metrics_expression_is_bounded PASSED
tests/test_pipeline_runtime.py::test_writer_dataset_creates_new_dataset_item SKIPPED
tests/test_pipeline_runtime.py::test_writer_dataset_updates_existing_dataset_preserving_metadata SKIPPED
tests/test_pipeline_runtime.py::test_writer_dataset_refuses_update_without_write_access SKIPPED
tests/test_pipeline_runtime.py::test_use_case_3_incidents_near_schools_by_commune SKIPPED
tests/test_pipeline_runtime.py::test_execute_qgis_transform_raises_clean_error_without_worker_url PASSED
tests/test_pipeline_runtime.py::test_execute_qgis_transform_computes_centroids SKIPPED

11 passed, 6 skipped in 1.59s
```

(5 pre-existing postgis-marked skips + 1 new qgis-marked skip = 6, as
expected — no regressions.)

## Full core suite

```
1023 passed, 126 skipped in 61.53s (0:01:01)
```

Baseline stated in the task was 1022 passed / 125 skipped. Result is exactly
+1/+1 (the new `test_execute_qgis_transform_raises_clean_error_without_worker_url`
passes, the new `test_execute_qgis_transform_computes_centroids` skips) — no
collateral regressions.

## Files changed

- `core/app/pipelines/runtime.py`
- `core/tests/test_pipeline_runtime.py`

## Self-review

- **Completeness**: Steps 1-4 done and verified for real (RED then GREEN
  shown above); Step 5's test code written verbatim per brief; Step 6's
  non-sidecar half verified (clean skip); Step 7 (full file) and the full
  suite both run and green; Step 8 committed.
- **Quality**: new dispatch branch placed exactly where the brief specifies
  (inside the existing `for node in ordered:` loop of
  `_execute_transform_chain`, right after `output_srid` is computed via
  `compiler.transform_output_srid`, before the `view_by_node`/`srid_by_node`
  bookkeeping that's shared by both the qgis and non-qgis paths). The
  `if node.op == "transform.qgis": ... else: ...` structure keeps the
  non-qgis path textually identical to before (same `compile_transform_sql`
  call, same `CREATE TEMP VIEW`), satisfying "no behavior change to the
  other transform ops' existing dispatch logic".
- **Discipline**: only `core/app/pipelines/runtime.py` and
  `core/tests/test_pipeline_runtime.py` touched, matching the task's file
  list exactly. No other files modified, no extra scope (e.g. did not touch
  `routes.py`/`jobs.py`, which is explicitly Task 6's job of consuming these
  new keyword params).
- **Testing**: pristine output at every step (RED confirmed the exact
  brief-predicted raw `ValueError`; GREEN confirmed the exact
  `PipelineRuntimeError` message match; full file and full suite runs used
  real DuckDB execution via the existing fixtures, no mocking of the
  runtime logic itself — only `_require_readable_collection_id`/
  `_table_info_for_collection` are monkeypatched, exactly as every other
  test in this file already does).

## Issues / concerns

1. **Brief discrepancy (test payload missing writer node)** — documented
   above; fixed by adding a minimal `writer.export` node + edge to both new
   tests, following the established pattern of every other test in this
   file. This is a correction to the brief's literal test code, not a
   deviation in intent — the test still asserts exactly what the brief
   describes (clean `PipelineRuntimeError` mentioning `QGIS_WORKER_URL`,
   raised before any I/O).
2. **Deferred real-sidecar verification** — per this session's explicit
   scope, `test_execute_qgis_transform_computes_centroids` was never run
   against a live `qgis-worker` container. Its correctness (that
   `native:centroids` via the sidecar actually returns the two expected
   centroids `(1.0, 1.0)` and `(11.0, 11.0)`) is unverified. A future
   session with `/scratch` access and the Task 4 container running (`export
   CORE_TEST_QGIS_WORKER_URL=http://localhost:8300`) must run this before
   Task 8 relies on it as proof the whole chain works end to end.
3. The `import shutil` inside `_execute_qgis_transform` (rather than at
   module top) is per the brief's exact code; left as specified rather than
   moved to the top-level import block, since the brief calls this out as
   the exact code to add.
