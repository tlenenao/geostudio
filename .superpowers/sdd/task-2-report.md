# Task 2 report — Core: `geom_intersects` on the OGC API Features endpoint (SP-14n)

## What I implemented

- `core/app/features/repository.py`:
  - `_where(session, info, bbox, geom_intersects, filters)` gained a new
    `geom_intersects` parameter (positional, inserted between `bbox` and
    `filters`). When `geom_intersects` is not `None`: raises
    `FilterError("geom_intersects", "collection has no geometry")` if
    `info.geometry_column is None`; otherwise appends an
    `ST_Intersects(<geom_col>, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:gi), 4326), :gisrid))`
    clause, with `gi` = `json.dumps(geom_intersects)` and `gisrid` =
    `info.srid or 4326` — same CRS-transform pattern already used for `bbox`.
  - `select_features(...)` gained a `geom_intersects=None` keyword parameter,
    forwarded to `_where`.
  - No new import needed (`json` was already imported at the top of the file).
- `core/app/features/routes.py`:
  - `import json` added alongside `os`.
  - `RESERVED_QUERY_PARAMS` extended with `"geom_intersects"`.
  - New `_parse_geom_intersects(raw)` helper (placed right after
    `_parse_bbox`): returns `None` for `raw is None`; on `json.loads` failure
    or when the parsed value isn't a dict with both `"type"` and
    `"coordinates"` keys, raises a 400 via `_validation_error` with
    `code: "invalid_geom_intersects"`.
  - `list_features` gained a `geom_intersects: str | None = None` query
    parameter, parses it via `_parse_geom_intersects`, and forwards the
    parsed dict to `repo.select_features(..., geom_intersects=parsed_geom_intersects, ...)`.
- Verified all other internal callers of `select_features`
  (`app/stac/routes.py` x2, `app/mcp/tools.py`) pass `bbox`/`filters` as
  keyword arguments, so adding the new keyword-only `geom_intersects=None`
  parameter is fully backward compatible — no other call site needed changes.

Implementation matches the brief's literal code exactly; no deviations.

## What I tested and results

**Docker/postgis availability**: Docker was running with a dedicated
`postgis-test` container (`postgis/postgis:16-3.5` on `127.0.0.1:5433`,
matching the `CORE_TEST_DATABASE_URL` convention used elsewhere in this repo,
e.g. `scripts/measure_cdc_consumer_throughput.py` and
`tests/test_cdc_consumer_postgis.py`). I set
`CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test`
and the postgis-marked tests **ran for real** (not skipped) against a live
PostGIS instance, both at RED and GREEN.

- `core/tests/test_features_repository.py -m postgis`: 16/16 passed with the
  DB URL set (14 pre-existing + 2 new), including
  `test_geom_intersects_filters_by_exact_polygon` and
  `test_geom_intersects_without_geometry_column_raises`.
- `core/tests/test_features_routes_read.py` (no docker needed, in-memory
  sqlite + fake repo): 7/7 passed, including the new
  `test_geom_intersects_parsing`.
- Full suite with `CORE_TEST_DATABASE_URL` set: `997 passed` (0 failed, 0
  skipped) in ~154s.
- Full suite without the DB URL (baseline/CI-like run, matching what most
  environments will see): `883 passed, 114 skipped` in ~95s — consistent with
  the repo's documented baseline (previously 606+87 skipped; grown by prior
  SP-14n tasks and this task's 2 new postgis tests).

## TDD Evidence

**RED — repository layer** (with real PostGIS via `CORE_TEST_DATABASE_URL`):

```
$ CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest tests/test_features_repository.py -k geom_intersects -v -m postgis
tests/test_features_repository.py::test_geom_intersects_filters_by_exact_polygon FAILED
tests/test_features_repository.py::test_geom_intersects_without_geometry_column_raises FAILED
E  TypeError: select_features() got an unexpected keyword argument 'geom_intersects'
2 failed, 14 deselected in 0.71s
```

Exactly the failure the brief predicted. (Without the DB URL set, the same
run SKIPs both tests with reason `CORE_TEST_DATABASE_URL non défini — test
postgis skippé`, confirming the postgis-marker gating works as documented —
but docker/postgis being available here meant I could actually exercise
these as true RED failures, not just skips.)

**RED — route layer** (no docker needed):

```
$ uv run pytest tests/test_features_routes_read.py -v
tests/test_features_routes_read.py::test_geom_intersects_parsing FAILED
E  AssertionError: assert None == {'type': 'Point', 'coordinates': [1.0, 2.0]}
1 failed, 6 passed in 5.85s
```

`repo.calls["geom_intersects"]` was `None` because the unrecognized query
param was silently ignored by FastAPI (not yet declared on `list_features`),
exactly as predicted.

**GREEN — repository layer**:

```
$ CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest tests/test_features_repository.py -v -m postgis
16 passed in 1.51s
```

**GREEN — route layer**:

```
$ uv run pytest tests/test_features_routes_read.py -v
7 passed in 4.69s
```

## Files changed

- `core/app/features/repository.py` — `_where` + `select_features` gain `geom_intersects`.
- `core/app/features/routes.py` — `import json`, `RESERVED_QUERY_PARAMS`, `_parse_geom_intersects`, `list_features`.
- `core/tests/test_features_repository.py` — `from dataclasses import replace` import + 2 new postgis-marked tests.
- `core/tests/test_features_routes_read.py` — `import json`, `make_fake_repo`'s `select_features` signature updated, 1 new test.

Commit: see below.

## Self-review

- **Completeness**: both new repository tests and the route test pass; the
  "no geometry column" edge case (`FilterError`) is covered; malformed-JSON
  and well-formed-but-not-a-geometry-dict cases both return 400
  `invalid_geom_intersects` at the route layer.
- **Quality**: code is byte-for-byte what the brief specified, matching the
  existing `bbox` pattern in both files (same CRS-transform idiom, same
  `_validation_error` helper, same French inline comment style for the
  SP-14n rationale).
- **Discipline**: no scope creep — only the 4 target files touched, exactly
  the interfaces specified (`geom_intersects` as a plain keyword arg with
  `None` default, inserted in the same position as in the brief).
- **Testing**: real HTTP requests through `TestClient` for the route test;
  real SQL against live PostGIS (not mocked) for the repository tests —
  actually exercised (not skipped) since docker was available. No stray
  warnings introduced (the pre-existing `procrastinate.exceptions.AppNotOpen`
  log noise during collection creation in the sqlite route tests is
  unrelated pre-existing behavior in `app/collections/repository.py`'s
  embedding-enqueue path, present before this change too).

## Issues or concerns

None. Docker/postgis was available and both new postgis-marked tests were
verified to actually pass against a real database, not merely skip — a
stronger verification than the brief's minimum bar.
