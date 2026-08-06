# Task 8 report — End-to-end integration test (full pipeline through the sidecar)

## What was implemented

Appended one test to `core/tests/test_pipeline_runtime.py`, exactly as
specified in the task brief (Step 1), verbatim, no deviations:

`test_transform_qgis_end_to_end_dissolve_then_write(pg_engine, monkeypatch, tmp_path, qgis_worker_url)`

Marked `@pytest.mark.postgis` and `@pytest.mark.qgis`. It exercises the full
chain `reader.collection` (2 adjacent squares sharing the edge `x=1`, same
`region="a"`) -> `transform.qgis` (`native:dissolve`, grouped by `FIELD:
region`) -> `writer.collection`, via the real `runtime.run_pipeline`
against a real Postgres database and a real `qgis-worker` sidecar. Asserts
the dissolved output collapses to 1 row with `region="a"`, and that the
returned stats include a `writer.collection` stat with `rowCount == 1`.
Cleans up with `DROP TABLE dissolved_out` + `TRUNCATE ... CASCADE` at the
end, matching the existing postgis-test-cleanup pattern used by
`test_use_case_3_incidents_near_schools_by_commune` and the other
postgis-marked tests in this file.

This is a pure test-only change — no production code touched.

## Step 2 — confirm it skips cleanly without infra

Ran with no `CORE_TEST_DATABASE_URL` / `CORE_TEST_QGIS_WORKER_URL` /
`CORE_TEST_QGIS_SCRATCH_DIR` set:

```
$ cd core && uv run pytest tests/test_pipeline_runtime.py -k transform_qgis_end_to_end -v
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
collecting ... collected 18 items / 17 deselected / 1 selected

tests/test_pipeline_runtime.py::test_transform_qgis_end_to_end_dissolve_then_write SKIPPED [100%]

====================== 1 skipped, 17 deselected in 0.67s =======================
```

Skipped cleanly (not an error), as required. Per the task instructions,
Step 3 (running against real infra: writable `/scratch` + a live
`qgis-worker` sidecar) was explicitly **not** attempted this session — no
`sudo` access to create/mount `/scratch`, and no running sidecar container.

## Step 4 — full core suite + lint-imports (no env vars set)

```
$ cd core && uv run pytest -q
1025 passed, 127 skipped in 62.52s (0:01:02)
```

Matches expectation exactly: 1025 passed (unchanged), 127 skipped (126
pre-existing + 1 new skip for this test), 0 failures, 0 errors.

```
$ cd core && uv run lint-imports
Analyzed 138 files, 399 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

Clean, as expected — the test imports nothing new beyond what's already
imported elsewhere in the same file (`app.pipelines.runtime`,
`app.configs.schemas.PipelinePayload`, `app.collections.ddl.
apply_collection_ddl`, etc.), all already covered by the existing
layered-architecture contract.

## Files changed

- `core/tests/test_pipeline_runtime.py` — +97 lines, one new test appended
  at the end of the file. No other file touched.

Commit: `0e01da5` — `test(core): end-to-end scenario for transform.qgis
dissolve -> writer.collection`

## Self-review

- **Completeness**: test written verbatim per the brief (diff matches the
  brief's code block character-for-character, modulo the surrounding blank
  lines needed to append after the previous test). Skips cleanly with no
  infra. Full suite green with the expected new skip count. `lint-imports`
  clean.
- **Quality**: matches the existing pattern in this file — `pg_engine` +
  `Base.metadata.create_all` + `make_session_factory` + tenant/user
  bootstrap + raw `INSERT INTO collections` + `CREATE TABLE` +
  `apply_collection_ddl` for the writer-side table, `dataclasses.replace`
  on the shared `TABLE_INFO` fixture for both the reader and writer table
  info, `monkeypatch.setattr` for `_table_info_for_collection` and
  `_require_readable_collection_id`, `_write_partition` for the reader-side
  GeoParquet partition, `PipelinePayload.model_validate` for the pipeline
  definition, `runtime.run_pipeline` call with all required kwargs
  including `qgis_worker_url`, and the `DROP TABLE` + `TRUNCATE ...
  CASCADE` cleanup block at the end inside `pg_engine.begin()` — identical
  in shape to `test_use_case_3_incidents_near_schools_by_commune` and the
  other postgis-marked writer tests earlier in the file.
- **Discipline**: only `core/tests/test_pipeline_runtime.py` touched,
  confirmed via `git diff --stat` before commit (1 file changed, 97
  insertions) and `git status` after commit (no other files staged or
  modified by this task; the pre-existing unrelated modifications to
  `.superpowers/sdd/*` and `docs/superpowers/plans/*` predate this task and
  were left untouched). No production code changed — this is the one pure
  test task in the SP-15d plan.

## Issues / concerns

- As instructed, Step 3 (running this test against real infra — real
  Postgres + real `qgis-worker` sidecar with a shared writable `/scratch`)
  was **not** performed this session, since neither a writable `/scratch`
  (requires interactive `sudo`, unavailable here) nor a running
  `qgis-worker` container is available. This means the test's actual
  correctness — whether `native:dissolve` on two adjacent squares sharing
  an edge, grouped by `region="a"`, really produces one `MultiPolygon`
  feature written through the unchanged `writer.collection` path into
  `dissolved_out` — remains **unverified** pending a future session with
  both `sudo`/`/scratch` access and a running sidecar.
- Because this is Task 8 of 8, the **last** task in the SP-15d plan, this
  same deferral applies to the plan's overarching claim: "`transform.qgis`
  actually works end-to-end against a real `qgis_process` sidecar" has
  never been exercised for real in any of Tasks 1–8. Every prior qgis-marked
  test in this file (e.g. `test_execute_qgis_transform_computes_centroids`)
  and this new one are all skip-only in every session run so far. A future
  session with `/scratch` write access and a running `qgis-worker`
  container needs to run Step 3 (and the equivalent for the other
  qgis-marked tests) before the "sidecar composes end-to-end" claim in the
  plan's design doc can be considered verified rather than merely
  type-checked/skip-tested.
- No other concerns. The test file's existing helpers/fixtures
  (`pg_engine`, `Base`, `make_session_factory`, `get_or_create_default_tenant`,
  `get_or_create_user`, `apply_collection_ddl`, `TABLE_INFO`, `ColumnInfo`,
  `_write_partition`, `dataclasses`, `text`, `qgis_worker_url`) all existed
  exactly as the brief assumed — no mismatch found, no escalation needed.
