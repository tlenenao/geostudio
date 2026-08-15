# Task 4 report — `app.appexport.snapshot.write_snapshot`

## What I did

Followed TDD exactly per the brief (`.superpowers/sdd/task-4-brief.md`):

1. Read the full brief, including the exact test file and module content
   provided verbatim.
2. Verified the interfaces the brief claims exist, actually exist and match
   the signatures used in the brief's code, before writing anything:
   - `app/appexport/manifest.py` — `CollectionSnapshotEntry`, `write_manifest`,
     `read_manifest` (Task 3 output, already present on disk).
   - `app/appexport/freeze.py` — confirmed the same
     `introspect_table` + `select_features` under `rls_scope` in-process
     pattern this task's module reuses.
   - `app/cdc/parquet_writer.py` — `ChangeRow` dataclass fields
     (`op, lsn, ts, pk_column, pk_value, columns, geometry_column,
     geometry_wkb_hex`) and `write_geoparquet(rows, *, srid, path)`.
   - `app/collections/schema_json.py` — `table_info_to_schema(info) -> dict`.
   - `app/features/repository.py` — `select_features(session, info, *, limit,
     offset, bbox=None, geom_intersects=None, filters=None) -> FeaturePage`.
   - `app/collections/repository.py` — `get_collection(session, *, tenant_id,
     collection_id)`.
   All matched the brief exactly — no adjustments needed.
3. Created `core/tests/test_appexport_snapshot.py` verbatim from the brief
   (4 `@pytest.mark.postgis` tests: empty data sources, a features source
   written as GeoParquet + manifest, a zero-row collection producing no
   parquet file, and the same collection referenced by two DataSources
   being written only once).
4. Ran the test with `CORE_TEST_DATABASE_URL` set — confirmed it failed with
   `ModuleNotFoundError: No module named 'app.appexport.snapshot'` (a real
   collection error, not a skip — proof the env var was reaching pytest and
   postgis fixtures were engaging, since `app.main` import logged
   procrastinate task registration).
5. Created `core/app/appexport/snapshot.py` verbatim from the brief.
6. Re-ran the test — all 4 passed for real (2.37s) against Postgres.
7. Sanity-checked the skip/pass gating by re-running with the env var
   unset — all 4 correctly SKIPPED, confirming the pass in step 6 was a
   genuine real-database run and not a coincidence of some other default.
8. Self-reviewed the diff (`git diff --cached --stat`): only the two new
   files, 278 insertions, 0 modifications to any existing file — matches the
   brief's stated scope exactly.
9. Committed with the exact message from the brief's Step 5.

## Full test output

### Step 2 — before creating the module (env var set, expect ModuleNotFoundError, not skip)

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/lenen/projets/geostudio/core
configfile: pyproject.toml
plugins: anyio-4.14.1, pytest_httpserver-1.1.5
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
______________ ERROR collecting tests/test_appexport_snapshot.py _______________
ImportError while importing test module '/home/lenen/projets/geostudio/core/tests/test_appexport_snapshot.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.14/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_appexport_snapshot.py:12: in <module>
    from app.appexport.snapshot import write_snapshot
E   ModuleNotFoundError: No module named 'app.appexport.snapshot'
------------------------------- Captured stdout --------------------------------
{"timestamp": "2026-08-15T19:24:53", "level": "INFO", "logger": "procrastinate.blueprints", "message": "Adding tasks from blueprint", "trace_id": null, "span_id": null}
{"timestamp": "2026-08-15T19:24:53", "level": "INFO", "logger": "procrastinate.periodic", "message": "Registering task app.harvest.jobs.run_harvest_sweep_task with periodic id '' to run periodically with cron */15 * * * *", "trace_id": null, "span_id": null}
{"timestamp": "2026-08-15T19:24:54", "level": "INFO", "logger": "procrastinate.periodic", "message": "Registering task app.pipelines.jobs.run_pipeline_sweep_task with periodic id '' to run periodically with cron */5 * * * *", "trace_id": null, "span_id": null}
=========================== short test summary info ============================
ERROR tests/test_appexport_snapshot.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 1.86s ===============================
```

### Step 4 — after creating the module (env var set, expect PASS for real)

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/lenen/projets/geostudio/core
configfile: pyproject.toml
plugins: anyio-4.14.1, pytest_httpserver-1.1.5
collecting ... collected 4 items

tests/test_appexport_snapshot.py::test_no_data_sources_writes_empty_manifest PASSED [ 25%]
tests/test_appexport_snapshot.py::test_features_source_is_written_as_geoparquet PASSED [ 50%]
tests/test_appexport_snapshot.py::test_collection_with_no_rows_writes_no_parquet_file PASSED [ 75%]
tests/test_appexport_snapshot.py::test_same_collection_referenced_twice_is_written_once PASSED [100%]

============================== 4 passed in 2.37s ===============================
```

### Sanity check — env var unset (expect all 4 SKIPPED, confirming step 4 was genuinely a real-DB run)

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0 -- /home/lenen/projets/geostudio/core/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/lenen/projets/geostudio/core
configfile: pyproject.toml
plugins: anyio-4.14.1, pytest_httpserver-1.1.5
collecting ... collected 4 items

tests/test_appexport_snapshot.py::test_no_data_sources_writes_empty_manifest SKIPPED [ 25%]
tests/test_appexport_snapshot.py::test_features_source_is_written_as_geoparquet SKIPPED [ 50%]
tests/test_appexport_snapshot.py::test_collection_with_no_rows_writes_no_parquet_file SKIPPED [ 75%]
tests/test_appexport_snapshot.py::test_same_collection_referenced_twice_is_written_once SKIPPED [100%]

============================== 4 skipped in 1.74s ==============================
```

## Deviations from the brief

None. Both the test file and `snapshot.py` were created exactly as specified
in the brief's Step 1 and Step 3 code blocks, verbatim. All interfaces the
brief assumed (`CollectionSnapshotEntry`/`write_manifest` from Task 3,
`ChangeRow`/`write_geoparquet`, `table_info_to_schema`, `select_features`,
`rls_scope`, `collections_repo.get_collection`) were verified against the
real, current signatures in the codebase before use and matched without any
adjustment needed.

## Self-review notes

- `git diff --cached --stat` confirms the change is scoped to exactly the
  two files named in the brief: `core/app/appexport/snapshot.py` (106 lines)
  and `core/tests/test_appexport_snapshot.py` (172 lines), 278 insertions,
  0 deletions, 0 other files touched. No existing file was modified.
- Confirmed the `ModuleNotFoundError` failure in Step 2 was a genuine
  collection-time error (not a skip) — the captured stdout shows
  `app.main` import succeeding (procrastinate periodic tasks registered),
  which only happens when the postgis fixtures/session machinery is
  actually engaging, i.e. `CORE_TEST_DATABASE_URL` was correctly reaching
  pytest.
- Confirmed the inverse: with the env var unset, all 4 tests SKIP rather
  than error or pass — this rules out the possibility that the PASS in
  Step 4 was accidentally running against SQLite or some other fallback
  instead of real Postgres.
- Logic sanity-checked against the module's own docstring claims:
  - Zero-row collections produce no parquet file (`if rows:` guard) but
    still get a manifest entry with `featureCount: 0` — matches
    `test_collection_with_no_rows_writes_no_parquet_file`.
  - Same collection referenced by two DataSources (one `"features"`, one
    `"statistics"`) is deduplicated via the `seen` set keyed by
    `collection_id` — matches
    `test_same_collection_referenced_twice_is_written_once`.
  - Every row gets `op="insert"`, `lsn=0` — the CDC-shaped
    "a snapshot is a change-log of nothing but inserts" framing that lets
    `run_collection_aggregate`'s existing hive-partition glob/CTE
    dedup logic read snapshot partitions unmodified.
  - Partition path exactly matches
    `{snapshot_dir}/snapshot/tenant_id=.../collection_id=.../dt=snapshot/data.parquet`
    as asserted by the test and required by
    `app.analytics.aggregate.run_collection_aggregate`'s expected layout.
- No full test suite run — per the task scope, this task only adds two new
  files and touches nothing existing, so the scoped run
  (`tests/test_appexport_snapshot.py`) is sufficient evidence.

## Commit

`5009aaf` — `feat(core): write_snapshot — GeoParquet snapshot per collection (SP-18c)`
