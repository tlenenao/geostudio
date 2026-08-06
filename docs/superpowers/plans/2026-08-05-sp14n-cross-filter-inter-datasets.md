# SP-14n — Cross-filter inter-datasets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a dataset declare a `crossFilterLinks` entry pointing at another dataset (attribute match or spatial intersection) so that selecting an entity/value on a widget bound to dataset A also cross-filters widgets bound to the *linked* dataset B — not just widgets on the same dataset, which is all SP-14b delivered.

**Architecture:** `CrossFilterLink` (attribute | spatial) is a new opt-in field on `DatasetConfig`, declared the same way as `reactsToExtent` (A29). `CrossFilterEntry` gains an optional `geometry` field, populated only by widgets that click an actual mapped feature (Carte, Table/Liste when the record has one) — chart/pivot clicks never carry one, since they select an aggregated group, not a feature. `derivePatch` (`analyticsPatch.ts`) is extended to also resolve, for every *other* active cross-filter, whether its origin dataset declares a link to the current source's dataset, and if so translate it into a query patch (attribute: `targetField=value` same as today; spatial/bbox: a client-computed bounding box reusing the existing `bbox` query key; spatial/exact: a new `geomIntersects` key). The core gains a generic `geom_intersects` capability (GeoJSON, `ST_Intersects`) on both the OGC API Features endpoint (Postgres) and the DuckDB aggregate endpoint — mirroring the existing `bbox` capability on both, including its documented limitation that only the aggregate/statistics path actually receives it from the shell today (`analytics-context.spec.ts` scenario 2: "spec §3 : c'est le consommateur réel du bbox"). This plan follows that same precedent rather than reopening it.

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/DuckDB (`core/`), React/TypeScript/React Query (`shell/`), Playwright E2E.

## Global Constraints

- Additive only: `crossFilterLinks` defaults to `[]`/absent everywhere; no existing dataset has it; existing E2E specs stay green unmodified.
- TDD: write the failing test before the implementation, for every step below.
- Conventional commits (`feat(core): …`, `feat(shell): …`), one subject each, small.
- Docs and commit messages in French; code/identifiers in English (per `CLAUDE.md`).
- Out of scope (do not implement): visual query builder (blocked on SP-15), transitive/chained propagation (A→B→C), automatic link reciprocity, cross-dataset collision resolution beyond "last resolved wins", persisting cross-filter geometry in the URL or a bookmark.
- The spatial-cross-filter's `geomIntersects` patch only ever reaches the server via the aggregate/statistics path (`buildAggregateBody`) in this plan — mirroring the pre-existing `bbox` precedent documented in `analytics-context.spec.ts` scenario 2. Do **not** attempt to also wire it (or `bbox`) into `_queryParams`/`buildFeaturesUrl` — that would be reopening a decision SP-14b already made deliberately, not a bug to fix here.

---

## Task 1: Core — `geomIntersects` on the DuckDB aggregate endpoint

**Files:**
- Modify: `core/app/analytics/aggregate.py:1-20` (add `import json`, extend `AggregateRequestBody`), `:78-104` (`_validate_fields`), `:142-167` (`_build_where`)
- Test: `core/tests/test_analytics_aggregate.py` (append)

**Interfaces:**
- Produces: `AggregateRequestBody.geomIntersects: dict | None = None` (a GeoJSON geometry dict) — validated (raises `UnknownAggregateField("geomIntersects", ...)` when the collection has no geometry) and applied as `ST_Intersects(<geom col>, ST_GeomFromGeoJSON(?))` in the DuckDB WHERE clause, same pattern as the existing `bbox` field right above it.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_analytics_aggregate.py`, right after `test_bbox_filter_narrows_rows_spatially` (and its neighbor `test_bbox_without_geometry_column_raises` a few lines down — insert after that one instead, to keep the two "without geometry" tests adjacent):

```python
def test_geom_intersects_filter_narrows_rows_spatially(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1, x=2.3, y=48.8),  # dans le polygone
        _row(2, "Sud", "2025", 5, lsn=1, x=100.0, y=50.0),  # hors polygone
    ])
    polygon = {
        "type": "Polygon",
        "coordinates": [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]],
    }
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", geomIntersects=polygon)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_geom_intersects_without_geometry_column_raises():
    info_no_geom = TableInfo(table_name="t", pk_column="id", geometry_column=None,
                             geometry_type=None, srid=None, columns=[])
    request = AggregateRequestBody(geomIntersects={"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            duckdb.connect(":memory:"), base_uri="/nonexistent", tenant_id="t1",
            collection_id="c", table_info=info_no_geom, request=request,
        )
    assert exc_info.value.field == "geomIntersects"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k geom_intersects -v`
Expected: FAIL — `AggregateRequestBody` has no field `geomIntersects` (Pydantic ignores unknown fields by default, so it's silently dropped and the WHERE clause never filters — the first test's assertion on `rows` fails because both rows are summed: `[{"region": "Nord", "value": 10}]` vs actual `[{"region": "Nord", "value": 10}, {"region": "Sud", "value": 5}]`; the second test fails because no `UnknownAggregateField` is ever raised).

- [ ] **Step 3: Implement**

In `core/app/analytics/aggregate.py`, add the import (line 15, alongside the existing one):

```python
import json
from typing import Literal
```

Extend `AggregateRequestBody` (right after `bbox`):

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    geomIntersects: dict | None = None
    bucket: Literal["day", "week", "month"] | None = None
    bins: int | None = None
```

In `_validate_fields`, right after the existing bbox check:

```python
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")
    if request.geomIntersects is not None and not table_info.geometry_column:
        raise UnknownAggregateField("geomIntersects", "collection has no geometry")
```

In `_build_where`, right after the existing bbox clause:

```python
    if request.bbox is not None:
        minx, miny, maxx, maxy = request.bbox
        # Native GEOMETRY : la colonne géométrie du GeoParquet CDC est déjà
        # lue par DuckDB comme un type GEOMETRY (spike Task 1, vérifié
        # contre MinIO réel) — pas de ST_GeomFromWKB(...) ici.
        clauses.append(
            f"ST_Intersects({_qi(table_info.geometry_column)}, "
            f"ST_MakeEnvelope(?, ?, ?, ?))"
        )
        params.extend([minx, miny, maxx, maxy])
    if request.geomIntersects is not None:
        # SP-14n : intersection géométrique exacte, complément précis du bbox
        # ci-dessus (rectangle). Même colonne, même opérateur ST_Intersects —
        # seule la forme du second argument change (GeoJSON arbitraire, pas
        # une enveloppe rectangulaire).
        clauses.append(
            f"ST_Intersects({_qi(table_info.geometry_column)}, "
            f"ST_GeomFromGeoJSON(?))"
        )
        params.append(json.dumps(request.geomIntersects))
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k geom_intersects -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full aggregate test file**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`
Expected: all tests pass (previous tests + 2 new ones), no regressions.

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): geomIntersects filter on the DuckDB aggregate endpoint (SP-14n)"
```

---

## Task 2: Core — `geom_intersects` on the OGC API Features endpoint

**Files:**
- Modify: `core/app/features/repository.py:8-17` (no new import needed, `json` already imported), `:66-99` (`_where`), `:120-124` (`select_features`)
- Modify: `core/app/features/routes.py:5,40,91-103,124-141` (`import json`, `RESERVED_QUERY_PARAMS`, new `_parse_geom_intersects`, `list_features`)
- Test: `core/tests/test_features_repository.py` (append, postgis-marked), `core/tests/test_features_routes_read.py` (append, no docker needed)

**Interfaces:**
- Produces: `select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None)` — `geom_intersects` is a GeoJSON dict, translated to `ST_Intersects(<geom>, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(...), 4326), <srid>))`; raises `FilterError("geom_intersects", "collection has no geometry")` when the collection has none. `GET /collections/{id}/items?geom_intersects=<url-encoded GeoJSON>` parses and forwards it the same way `bbox` already does.

- [ ] **Step 1: Write the failing repository tests (postgis-marked)**

Append to `core/tests/test_features_repository.py`, right after `test_pagination_and_bbox_and_filters`. Add the import at the top first:

```python
from dataclasses import replace

import pytest
from sqlalchemy import text
```

Then the tests:

```python
def test_geom_intersects_filters_by_exact_polygon(info, pg_session_factory):
    polygon = {
        "type": "Polygon",
        "coordinates": [[[0.5, 44.5], [1.5, 44.5], [1.5, 45.5], [0.5, 45.5], [0.5, 44.5]]],
    }
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, geom_intersects=polygon)
        assert [f["id"] for f in page.features] == [1]


def test_geom_intersects_without_geometry_column_raises(info, pg_session_factory):
    info_no_geom = replace(info, geometry_column=None)
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info_no_geom, limit=10, offset=0,
                            geom_intersects={"type": "Point", "coordinates": [0, 0]})
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_repository.py -k geom_intersects -v -m postgis`
Expected: FAIL if docker/postgis is available (`select_features() got an unexpected keyword argument 'geom_intersects'`); SKIPPED otherwise (postgis-marked, consistent with the other 87 skipped tests — see `CLAUDE.md`). If docker isn't running in this environment, proceed to Step 3 anyway and rely on Step 4's route-level test (no docker needed) plus a later run against docker before merging.

- [ ] **Step 3: Implement the repository layer**

In `core/app/features/repository.py`, extend `_where` (currently at line 66):

```python
def _where(session: Session, info: TableInfo, bbox, geom_intersects, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (raw_name, raw) in enumerate(sorted(filters.items())):
            name, suffix = _split_filter_key(raw_name)
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            ident = quote_ident(session, name)
            if suffix == "__in":
                values = raw.split(",")
                placeholders = []
                for j, value in enumerate(values):
                    key = f"f{i}_{j}"
                    params[key] = _coerce(col, value)
                    placeholders.append(f":{key}")
                clauses.append(f"{ident} IN ({', '.join(placeholders)})")
            elif suffix in _RANGE_OPS:
                clauses.append(f"{ident} {_RANGE_OPS[suffix]} :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
            else:
                clauses.append(f"{ident} = :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(f"{g} && ST_Transform(ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, 4326), :bsrid)")
        params.update({"bx0": bbox[0], "by0": bbox[1], "bx1": bbox[2],
                       "by1": bbox[3], "bsrid": info.srid or 4326})
    if geom_intersects is not None:
        # SP-14n : intersection géométrique exacte (ST_Intersects), complément
        # précis du bbox && ci-dessus (chevauchement d'enveloppes uniquement).
        if info.geometry_column is None:
            raise FilterError("geom_intersects", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(
            f"ST_Intersects({g}, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:gi), 4326), :gisrid))"
        )
        params.update({"gi": json.dumps(geom_intersects), "gisrid": info.srid or 4326})
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params
```

Update `select_features` (currently at line 120):

```python
def select_features(session: Session, info: TableInfo, *, limit: int, offset: int,
                    bbox=None, geom_intersects=None, filters=None) -> FeaturePage:
    t = quote_ident(session, info.table_name)
    where, params = _where(session, info, bbox, geom_intersects, filters)
```

(the rest of the function body is unchanged — only the call to `_where` gains the new argument).

- [ ] **Step 4: Run repository tests again**

Run: `cd core && uv run pytest tests/test_features_repository.py -v -m postgis`
Expected: PASS if docker is available (all tests in the file, including the 2 new ones); SKIPPED as a block otherwise.

- [ ] **Step 5: Write the failing route-level test (no docker needed)**

Append to `core/tests/test_features_routes_read.py`. Add `import json` at the top (line 1, alongside the existing imports), and update `make_fake_repo`'s `select_features` signature to accept and record the new parameter:

```python
def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox, geom_intersects=geom_intersects, filters=filters)
        if filters and "inconnu" in filters:
            raise FilterError("inconnu", "unknown filter property 'inconnu'")
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature,
                           calls=calls)
```

Then add the test, right after `test_bbox_parsing`:

```python
def test_geom_intersects_parsing(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    geom = {"type": "Point", "coordinates": [1.0, 2.0]}
    r = client.get("/collections/incidents/items", params={"geom_intersects": json.dumps(geom)})
    assert r.status_code == 200
    assert repo.calls["geom_intersects"] == geom
    r2 = client.get("/collections/incidents/items", params={"geom_intersects": "not-json"})
    assert r2.status_code == 400
    assert r2.json()["detail"]["errors"][0]["code"] == "invalid_geom_intersects"
```

- [ ] **Step 6: Run route tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: FAIL — `list_features` has no `geom_intersects` query parameter yet (unrecognized param is just ignored by FastAPI, so `repo.calls["geom_intersects"]` raises `KeyError`, and the malformed-JSON case returns 200 instead of 400).

- [ ] **Step 7: Implement the route layer**

In `core/app/features/routes.py`, add the import (line 5, alongside `os`):

```python
import json
import os
```

Extend `RESERVED_QUERY_PARAMS` (line 40):

```python
RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "geom_intersects", "f"}
```

Add `_parse_geom_intersects` right after `_parse_bbox` (around line 91):

```python
def _parse_geom_intersects(raw: str | None):
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise _validation_error(
            [{"field": "geom_intersects", "code": "invalid_geom_intersects",
              "message": "geom_intersects must be a GeoJSON geometry encoded as JSON"}])
    if not isinstance(parsed, dict) or "type" not in parsed or "coordinates" not in parsed:
        raise _validation_error(
            [{"field": "geom_intersects", "code": "invalid_geom_intersects",
              "message": "geom_intersects must be a GeoJSON geometry encoded as JSON"}])
    return parsed
```

Update `list_features` (around line 124):

```python
@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None, geom_intersects: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)
    try:
        with rls(session, col.tenant_id):
            page = repo.select_features(session, info, limit=limit, offset=offset,
                                        bbox=parsed_bbox, geom_intersects=parsed_geom_intersects,
                                        filters=filters or None)
    except FilterError as exc:
        raise _validation_error(
            [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
    return {
        "type": "FeatureCollection",
        "features": page.features,
        "numberMatched": page.number_matched,
        "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": _page_links(request, limit=limit, offset=offset, page=page),
    }
```

- [ ] **Step 8: Run route tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: PASS (all tests, including the new one).

- [ ] **Step 9: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: same baseline as before (606 + however many prior tasks added) plus 3 new tests (1 route-level, 2 postgis-marked — skipped without docker), no regressions.

- [ ] **Step 10: Commit**

```bash
git add core/app/features/repository.py core/app/features/routes.py core/tests/test_features_repository.py core/tests/test_features_routes_read.py
git commit -m "feat(core): geom_intersects filter on OGC API Features (SP-14n)"
```

---

## Task 3: Core — `crossFilterLinks` on `DatasetPayload`

**Files:**
- Modify: `core/app/configs/schemas.py:2-4` (`Annotated` import), `:95-102` (`DatasetPayload`, insert new models above it)
- Test: `core/tests/test_dataset_config_schema.py` (append)

**Interfaces:**
- Produces: `DatasetCrossFilterLinkAttribute(mode="attribute", targetDatasetId: str, sourceField: str, targetField: str)`, `DatasetCrossFilterLinkSpatial(mode="spatial", targetDatasetId: str, precision: Literal["bbox","exact"]="bbox")`, and `DatasetPayload.crossFilterLinks: list[...]` (discriminated union on `mode`, default `[]`). These are the exact names the shell's round-trip (Task 4) mirrors field-for-field, same convention as `BookmarkPayload` mirroring `AnalyticsContextState`.

- [ ] **Step 1: Write the failing schema tests**

Append to `core/tests/test_dataset_config_schema.py`:

```python
def test_dataset_config_cross_filter_links_default_empty():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.dataset.crossFilterLinks == []


def test_dataset_config_attribute_cross_filter_link():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {"mode": "attribute", "targetDatasetId": "ds-2", "sourceField": "commune", "targetField": "nom_commune"},
    ]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "attribute"
    assert link.targetDatasetId == "ds-2"
    assert link.sourceField == "commune"
    assert link.targetField == "nom_commune"


def test_dataset_config_spatial_cross_filter_link_defaults_to_bbox_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "spatial", "targetDatasetId": "ds-2"}]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "spatial"
    assert link.precision == "bbox"


def test_dataset_config_spatial_cross_filter_link_exact_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {"mode": "spatial", "targetDatasetId": "ds-2", "precision": "exact"},
    ]
    config = BuilderConfig.model_validate(body)
    assert config.dataset.crossFilterLinks[0].precision == "exact"


def test_dataset_config_cross_filter_link_unknown_mode_rejected():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "join", "targetDatasetId": "ds-2"}]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -k cross_filter -v`
Expected: FAIL — `DatasetPayload` has no field `crossFilterLinks` (Pydantic silently drops the unrecognized key by default, so `config.dataset.crossFilterLinks` raises `AttributeError`).

- [ ] **Step 3: Implement**

In `core/app/configs/schemas.py`, extend the import (line 2):

```python
from typing import Annotated, Literal
```

Insert right before `class DatasetPayload` (after `DatasetColumnMeta`):

```python
class DatasetCrossFilterLinkAttribute(BaseModel):
    mode: Literal["attribute"] = "attribute"
    targetDatasetId: str
    sourceField: str
    targetField: str


class DatasetCrossFilterLinkSpatial(BaseModel):
    mode: Literal["spatial"] = "spatial"
    targetDatasetId: str
    precision: Literal["bbox", "exact"] = "bbox"


DatasetCrossFilterLink = Annotated[
    DatasetCrossFilterLinkAttribute | DatasetCrossFilterLinkSpatial,
    Field(discriminator="mode"),
]
```

Extend `DatasetPayload` (add the field right after `reactsToExtent`):

```python
class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None
    arcgisItemId: str | None = None
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None
    reactsToExtent: bool = False
    crossFilterLinks: list[DatasetCrossFilterLink] = Field(default_factory=list)  # SP-14n
```

(the `_require_source_id` validator below is unchanged).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: PASS (all tests in the file, including the 5 new ones).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: same baseline plus 5 new tests, no regressions — `crossFilterLinks` is additive with a default, so every existing dataset payload (without it) still validates identically.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_dataset_config_schema.py
git commit -m "feat(core): crossFilterLinks on DatasetPayload (SP-14n)"
```

---

## Task 4: Shell — types (`CrossFilterLink`, `CrossFilterEntry.geometry`, `useSetCrossFilter`)

**Files:**
- Modify: `shell/src/api/types.ts:223-237` (`DatasetConfig`)
- Modify: `shell/src/builder/AnalyticsContext.tsx:4-5,19,62-72` (`CrossFilterEntry`, `SetCrossFilter`, `setCrossFilter`)
- Modify: `shell/src/api/itemClient.ts:197-231,584-599,632-655` (`ResolvedDataset`, `resolveDataset`, `createDatasetItem`, `getDatasetConfig`, `saveDatasetConfig`)
- Test: `shell/src/builder/AnalyticsContext.test.tsx` (append), `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Produces: `CrossFilterLink` (discriminated union, mirrors the core's `DatasetCrossFilterLink` field-for-field), `DatasetConfig.crossFilterLinks?: CrossFilterLink[]`, `CrossFilterEntry.geometry?: unknown`, `useSetCrossFilter()` returning a 5-arg setter `(datasetId, field, value, originSourceId, geometry?) => void`. Task 5 (`derivePatch`) and Task 6 (widget capture) both consume these exact names.

- [ ] **Step 1: Write the failing AnalyticsContext test**

Append to `shell/src/builder/AnalyticsContext.test.tsx`. First add a button to `Probe` that passes a geometry:

```typescript
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1", { type: "Point", coordinates: [1, 2] })}>set-cf-geom</button>
```

(insert it right after the existing `set-cf-range` button, inside the same `<div>`).

Then add the test, after `test("setCrossFilter accepts a {from,to} range value", ...)`:

```typescript
test("setCrossFilter stores an optional geometry alongside the entry", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf-geom"));
  expect(screen.getByText(/"geometry":\{"type":"Point","coordinates":\[1,2\]\}/)).toBeInTheDocument();
});

test("setCrossFilter without a geometry omits the field entirely (unchanged shape)", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.queryByText(/"geometry"/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: FAIL — `setCrossFilter` only accepts 4 arguments (TypeScript compile error) and never stores a `geometry` field.

- [ ] **Step 3: Implement in `AnalyticsContext.tsx`**

Change `CrossFilterEntry` (line 5):

```typescript
export type CrossFilterEntry = { field: string; value: CrossFilterValue; originSourceId: string; geometry?: unknown };
```

Change `SetCrossFilter` (line 19):

```typescript
type SetCrossFilter = (datasetId: string, field: string, value: CrossFilterValue, originSourceId: string, geometry?: unknown) => void;
```

Change `setCrossFilter` (currently at line 62-72):

```typescript
  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId, geometry) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId, geometry };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);
```

- [ ] **Step 4: Run the AnalyticsContext test to verify it passes**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: PASS (all tests in the file, including the 2 new ones — `JSON.stringify` naturally omits an `undefined` `geometry`, so the existing toggle/range tests are unaffected).

- [ ] **Step 5: Add `CrossFilterLink` to `types.ts`**

In `shell/src/api/types.ts`, extend `DatasetConfig` (currently lines 223-237):

```typescript
export type CrossFilterLink =
  | { targetDatasetId: string; mode: "attribute"; sourceField: string; targetField: string }
  | { targetDatasetId: string; mode: "spatial"; precision: "bbox" | "exact" };

export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
    };
```

- [ ] **Step 6: Write the failing itemClient round-trip test**

Append to `shell/src/api/itemClient.test.ts`, right after the existing `getDatasetConfig`/`saveDatasetConfig` tests (search the file for `"createDatasetItem"` or `"getDatasetConfig"` to find the neighboring tests and match their exact `server.use(...)`/`makeClient()` style):

```typescript
test("getDatasetConfig includes crossFilterLinks from the wire response", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds-1", kind: "dataset",
        config: {
          version: 1, kind: "dataset",
          dataset: {
            source: "collection", collectionId: "parcs", columns: {},
            crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "attribute", sourceField: "commune", targetField: "nom" }],
          },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "commune", targetField: "nom" },
  ]);
});

test("getDatasetConfig defaults crossFilterLinks to an empty array when absent from the wire", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds-1", kind: "dataset",
        config: { version: 1, kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([]);
});

test("saveDatasetConfig sends crossFilterLinks as-is and caches it for later reads", async () => {
  let posted: unknown;
  server.use(
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json(undefined, { status: 204 });
    }),
  );
  await makeClient().saveDatasetConfig("ds-1", {
    source: "collection", collectionId: "parcs", columns: {},
    crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" }],
  });
  expect((posted as { dataset: { crossFilterLinks: unknown } }).dataset.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" },
  ]);
});
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `getDatasetConfig` never reads/returns `crossFilterLinks` (TypeScript will also flag the `crossFilterLinks` property as unknown on the object literals used to call `saveDatasetConfig` once the type is defined, until Step 8 lands).

- [ ] **Step 8: Implement in `itemClient.ts`**

Extend `ResolvedDataset` (currently lines 197-204):

```typescript
  type ResolvedDataset = {
    source: "collection" | "arcgis";
    collectionId: string | null;
    arcgisItemId: string | null;
    columns: Record<string, DatasetColumnMeta>;
    timeField: string | null;
    reactsToExtent: boolean;
    crossFilterLinks: CrossFilterLink[];
  };
```

Extend `resolveDataset` (currently lines 207-231):

```typescript
  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: {
        dataset?: {
          source: "collection" | "arcgis";
          collectionId?: string | null; arcgisItemId?: string | null;
          columns?: Record<string, DatasetColumnMeta>;
          timeField?: string | null; reactsToExtent?: boolean;
          crossFilterLinks?: CrossFilterLink[];
        } | null;
      };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      source: dataset.source,
      collectionId: dataset.collectionId ?? null,
      arcgisItemId: dataset.arcgisItemId ?? null,
      columns: dataset.columns ?? {}, timeField: dataset.timeField ?? null,
      reactsToExtent: dataset.reactsToExtent ?? false,
      crossFilterLinks: dataset.crossFilterLinks ?? [],
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

Extend `createDatasetItem`'s `datasetCache.set(...)` call (currently lines 594-599):

```typescript
      datasetCache.set(String(data.itemId), {
        source: dataset.source,
        collectionId: dataset.source === "collection" ? dataset.collectionId : null,
        arcgisItemId: dataset.source === "arcgis" ? dataset.arcgisItemId : null,
        columns: {}, timeField: null, reactsToExtent: false, crossFilterLinks: [],
      });
```

Extend `getDatasetConfig` (currently lines 632-644):

```typescript
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      if (resolved.source === "arcgis" && resolved.arcgisItemId) {
        return {
          source: "arcgis", arcgisItemId: resolved.arcgisItemId, columns: resolved.columns,
          timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
          crossFilterLinks: resolved.crossFilterLinks,
        };
      }
      return {
        source: "collection", collectionId: resolved.collectionId ?? "", columns: resolved.columns,
        timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
        crossFilterLinks: resolved.crossFilterLinks,
      };
    },
```

Extend `saveDatasetConfig` (currently lines 646-655):

```typescript
    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns, timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
        crossFilterLinks: config.crossFilterLinks ?? [],
      });
    },
```

Add `CrossFilterLink` to the type import at the top of `itemClient.ts` (wherever `DatasetConfig`/`DatasetColumnMeta` are already imported from `./types`).

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests, including the 3 new ones).

- [ ] **Step 10: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions — every change is additive (new optional field, new optional callback parameter with a default of `undefined`).

- [ ] **Step 11: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/AnalyticsContext.tsx shell/src/api/itemClient.ts shell/src/builder/AnalyticsContext.test.tsx shell/src/api/itemClient.test.ts
git commit -m "feat(shell): CrossFilterLink type, cross-filter geometry, dataset round-trip (SP-14n)"
```

---

## Task 5: Shell — `bboxFromGeometry` util + `derivePatch` resolution

**Files:**
- Create: `shell/src/lib/geometryBbox.ts`
- Test: `shell/src/lib/geometryBbox.test.ts` (new)
- Modify: `shell/src/lib/analyticsPatch.ts` (full rewrite of `derivePatch`, factor out `applyCrossFilterValue`)
- Test: `shell/src/lib/analyticsPatch.test.ts` (append)

**Interfaces:**
- Consumes: `CrossFilterLink`, `DatasetConfig` (Task 4), `CrossFilterEntry.geometry` (Task 4).
- Produces: `bboxFromGeometry(geometry: unknown): [number, number, number, number] | null` (pure, no dependency on turf — none exists in this repo). `derivePatch` now also resolves inter-dataset links: attribute links translate to `targetField`/`targetField__in`/`targetField__gte`+`targetField__lte`; spatial/bbox links add `patch.bbox`; spatial/exact links add `patch.geomIntersects` (raw geometry object, consumed by Task 6's `buildAggregateBody` change).

- [ ] **Step 1: Write the failing `bboxFromGeometry` tests**

Create `shell/src/lib/geometryBbox.test.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { bboxFromGeometry } from "./geometryBbox";

test("returns a degenerate bbox for a Point", () => {
  expect(bboxFromGeometry({ type: "Point", coordinates: [2.4, 46.6] })).toEqual([2.4, 46.6, 2.4, 46.6]);
});

test("returns the enclosing bbox for a Polygon", () => {
  const polygon = {
    type: "Polygon",
    coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]],
  };
  expect(bboxFromGeometry(polygon)).toEqual([2.0, 48.0, 3.0, 49.0]);
});

test("returns the enclosing bbox across a MultiPolygon's parts", () => {
  const multi = {
    type: "MultiPolygon",
    coordinates: [
      [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
      [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
    ],
  };
  expect(bboxFromGeometry(multi)).toEqual([0, 0, 11, 11]);
});

test("returns null for undefined, null, or a non-geometry value", () => {
  expect(bboxFromGeometry(undefined)).toBeNull();
  expect(bboxFromGeometry(null)).toBeNull();
  expect(bboxFromGeometry({ foo: "bar" })).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement `geometryBbox.ts`**

Create `shell/src/lib/geometryBbox.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
// Recursively walks GeoJSON coordinate arrays (any depth: Point, LineString,
// Polygon, Multi*) to compute an enclosing [minX, minY, maxX, maxY] — no
// turf/geojson dependency, neither is present in this repo (DataRecord.geometry
// is typed `unknown` for the same reason, api/types.ts:351).
function walk(coords: unknown, acc: [number, number, number, number]): void {
  if (Array.isArray(coords) && typeof coords[0] === "number") {
    const [x, y] = coords as [number, number];
    if (x < acc[0]) acc[0] = x;
    if (y < acc[1]) acc[1] = y;
    if (x > acc[2]) acc[2] = x;
    if (y > acc[3]) acc[3] = y;
    return;
  }
  if (Array.isArray(coords)) coords.forEach((c) => walk(c, acc));
}

export function bboxFromGeometry(geometry: unknown): [number, number, number, number] | null {
  if (!geometry || typeof geometry !== "object" || !("coordinates" in geometry)) return null;
  const coords = (geometry as { coordinates: unknown }).coordinates;
  const acc: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  walk(coords, acc);
  if (!isFinite(acc[0])) return null;
  return acc;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the failing `derivePatch` tests**

Append to `shell/src/lib/analyticsPatch.test.ts`:

```typescript
const linked: DatasetConfig = {
  source: "collection", collectionId: "communes", columns: {},
  crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "attribute", sourceField: "commune", targetField: "nom_commune" }],
};

test("translates an attribute link from another dataset's active cross-filter", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({ nom_commune: "Brive" });
});

test("ignores an attribute link when the active field doesn't match sourceField", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "autre_champ", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({});
});

test("ignores a link that doesn't target this source's dataset", () => {
  const elsewhere = { ...linked, crossFilterLinks: [{ targetDatasetId: "ds-999", mode: "attribute" as const, sourceField: "commune", targetField: "nom_commune" }] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": elsewhere })).toEqual({});
});

test("translates a spatial/bbox link into a bbox patch derived from the entry's geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    bbox: "2,48,3,49",
  });
});

test("translates a spatial/exact link into a geomIntersects patch carrying the raw geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "exact" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    geomIntersects: polygon,
  });
});

test("ignores a spatial link when the active entry has no geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({});
});

test("does not resolve a link declared on the same dataset as the target source (no self-link)", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-1" } },
  };
  // dataset "ds-1" has no crossFilterLinks of its own here — this just proves the
  // direct same-dataset path (already tested above) and the link path don't double-fire.
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});
```

Add `DatasetConfig` to the file's type import from `../api/types` if not already present (it already is, per the file's existing `import type { DataSource, DatasetConfig } from "../api/types";`).

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: FAIL — `derivePatch` doesn't yet look at any dataset's `crossFilterLinks`, so every new "translates"/"ignores a link..." test that expects a non-empty patch gets `{}` instead.

- [ ] **Step 7: Implement `derivePatch`**

Replace the full contents of `shell/src/lib/analyticsPatch.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState, CrossFilterValue } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { bboxFromGeometry } from "./geometryBbox";

// Pure translation of the global analytics context into query-filter keys
// for one DataSource, mirroring the __gte/__lte/__in suffixes the core
// understands (features/repository.py, analytics/aggregate.py). `datasets`
// keys are DatasetConfig objects already resolved by the caller (DataContext)
// — this function never fetches.
export function derivePatch(
  source: DataSource,
  ctx: AnalyticsContextState,
  datasets: Record<string, DatasetConfig>,
): Record<string, unknown> {
  if (!source.datasetId) return {};
  const dataset = datasets[source.datasetId];
  if (!dataset) return {};

  const patch: Record<string, unknown> = {};

  if (ctx.timeRange && dataset.timeField) {
    patch[`${dataset.timeField}__gte`] = ctx.timeRange.from;
    patch[`${dataset.timeField}__lte`] = ctx.timeRange.to;
  }

  if (ctx.extent && dataset.reactsToExtent) {
    patch.bbox = ctx.extent.join(",");
  }

  const directCrossFilter = ctx.crossFilter[source.datasetId];
  if (directCrossFilter && directCrossFilter.originSourceId !== source.id) {
    applyCrossFilterValue(patch, directCrossFilter.field, directCrossFilter.value);
  }

  // SP-14n — cross-filter inter-datasets : pour chaque AUTRE dataset avec un
  // cross-filter actif, vérifier s'il déclare un lien vers le dataset de
  // cette source, et traduire en conséquence. Un seul saut (pas de chaînage
  // transitif) ; en cas de liens contradictoires vers la même cible, le
  // dernier résolu gagne (limite documentée, spec §1).
  for (const [originDatasetId, entry] of Object.entries(ctx.crossFilter)) {
    if (!entry || originDatasetId === source.datasetId) continue;
    const originDataset = datasets[originDatasetId];
    const link = originDataset?.crossFilterLinks?.find((l) => l.targetDatasetId === source.datasetId);
    if (!link) continue;
    if (link.mode === "attribute") {
      if (entry.field === link.sourceField) applyCrossFilterValue(patch, link.targetField, entry.value);
    } else if (entry.geometry !== undefined) {
      if (link.precision === "bbox") {
        const bbox = bboxFromGeometry(entry.geometry);
        if (bbox) patch.bbox = bbox.join(",");
      } else {
        patch.geomIntersects = entry.geometry;
      }
    }
  }

  return patch;
}

function applyCrossFilterValue(patch: Record<string, unknown>, field: string, value: CrossFilterValue): void {
  if (Array.isArray(value)) {
    patch[`${field}__in`] = value.join(",");
  } else if (typeof value === "object") {
    patch[`${field}__gte`] = value.from;
    patch[`${field}__lte`] = value.to;
  } else {
    patch[field] = value;
  }
}
```

Add `CrossFilterValue` to the existing import from `../builder/AnalyticsContext` in `analyticsPatch.test.ts` if a test references it directly (it doesn't need to — the tests above only construct plain object literals typed as `AnalyticsContextState`, already imported).

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: PASS (all tests, including the 7 new ones — the pre-existing same-dataset tests must still pass unchanged, since `applyCrossFilterValue` is a byte-for-byte extraction of the same three branches, not a behavior change).

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/lib/geometryBbox.ts shell/src/lib/geometryBbox.test.ts shell/src/lib/analyticsPatch.ts shell/src/lib/analyticsPatch.test.ts
git commit -m "feat(shell): resolve cross-filter links (attribute + spatial) in derivePatch (SP-14n)"
```

---

## Task 6: Shell — `geomIntersects` in the aggregate request body

**Files:**
- Modify: `shell/src/api/itemClient.ts:49-75` (`buildAggregateBody`)
- Test: `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Consumes: `DataSource.query.geomIntersects` (an object, set by Task 5's `derivePatch` for a spatial/exact link).
- Produces: `buildAggregateBody` forwards `query.geomIntersects` verbatim into `body.geomIntersects`, consumed server-side by Task 1's `AggregateRequestBody.geomIntersects`. `bbox` needs no change here — it already flows through `parseBboxQueryValue`, and Task 5's spatial/bbox patch reuses that same `bbox` key.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/api/itemClient.test.ts`, right after the existing `"queryDataSource sends a bbox query key as body.bbox, not as a filter"` test:

```typescript
test("queryDataSource sends a geomIntersects query key as body.geomIntersects", async () => {
  const geom = { type: "Point", coordinates: [1, 2] };
  let posted: { geomIntersects?: unknown } | undefined;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as { geomIntersects?: unknown };
      return HttpResponse.json({ categoryKey: "group", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "src-1", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", agg: "count", geomIntersects: geom },
  });
  expect(posted!.geomIntersects).toEqual(geom);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`
Expected: FAIL — `buildAggregateBody` never reads `query.geomIntersects`, so `posted!.geomIntersects` is `undefined`.

- [ ] **Step 3: Implement**

In `shell/src/api/itemClient.ts`, extend `buildAggregateBody` (right after the existing `bbox` block):

```typescript
function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (Array.isArray(query.groupBy)) body.groupBy = query.groupBy.map(String);
  else if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (query.bucket) body.bucket = String(query.bucket);
  if (query.bins) body.bins = Number(query.bins);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
  if (query.geomIntersects && typeof query.geomIntersects === "object") {
    body.geomIntersects = query.geomIntersects;
  }
  const filters: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      filters[k] = String(v);
    }
  }
  if (Object.keys(filters).length) body.filters = filters;
  return body;
}
```

(the generic `filters` loop already skips `geomIntersects` implicitly — its value is an object, and the loop's `typeof v === "string" || "number" || "boolean"` guard excludes it, exactly like `measures`/`bbox` today. No change to `STAT_KEYS` is needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`
Expected: PASS.

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): forward geomIntersects to the aggregate request body (SP-14n)"
```

---

## Task 7: Shell — capture geometry on feature click (Carte, Liste, Table)

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx:182-187` (`onFeatureClick`)
- Modify: `shell/src/builder/widgets/data.tsx:54-59` (list `selectRecord`), `:187-192` (table `selectRecord`)
- Test: `shell/src/builder/widgets/mapWidget.test.tsx` (extend existing test), `shell/src/builder/widgets/data.test.tsx` (extend existing test)

**Interfaces:**
- Consumes: `useSetCrossFilter()`'s new 5th `geometry` parameter (Task 4).
- Produces: every existing `setCrossFilter(datasetId, pkColumn, ..., dataSourceId)` call site in these two files now also passes the clicked record's `.geometry` (`unknown`, possibly `undefined` when the record has none) — chart.tsx and pivot.tsx are untouched, since they select an aggregated group value, never an individual feature's geometry.

- [ ] **Step 1: Extend the failing map test**

In `shell/src/builder/widgets/mapWidget.test.tsx`, extend the existing `CrossFilterProbe` in `test("map sets a cross-filter by pkColumn on feature click when dataset-bound", ...)` to also surface the geometry:

```typescript
test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value};geom=${JSON.stringify(entry.geometry ?? null)}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  ));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText('cf:id=1;geom={"type":"Point","coordinates":[5,6]}')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "cross-filter by pkColumn"`
Expected: FAIL — the rendered text is `cf:id=1;geom=null` (geometry not yet forwarded).

- [ ] **Step 3: Implement in `mapWidget.tsx`**

Change the `onFeatureClick` handler (currently lines 182-187):

```typescript
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn) {
                  setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""), record.geometry);
                }
              }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Extend the failing data.tsx tests**

In `shell/src/builder/widgets/data.test.tsx`, extend `CrossFilterProbe` and the table test to assert geometry propagation:

```typescript
function CrossFilterProbe({ datasetId }: { datasetId: string }) {
  const ctx = useAnalyticsContext();
  const entry = ctx.crossFilter[datasetId];
  return <p>cf:{entry ? `${entry.field}=${entry.value};geom=${JSON.stringify(entry.geometry ?? null)}` : "none"}</p>;
}

test("table row click forwards the record's geometry to the cross-filter entry when present", async () => {
  const Table = getWidget("table")!.Component;
  const data = {
    loading: false, error: false,
    records: [{ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } }],
    datasetId: "dataset-1", pkColumn: "id",
  };
  render(
    <AnalyticsContextProvider interactions="auto">
      <Table props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A").closest("tr")!);
  expect(await screen.findByText('cf:id=1;geom={"type":"Point","coordinates":[5,6]}')).toBeInTheDocument();
});
```

(the pre-existing `"table row click sets the cross-filter by pkColumn..."` test uses a record with no `geometry` key at all — leave it untouched; its probe now renders `geom=null` instead of nothing, which the test doesn't assert on, so it keeps passing.)

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx -t "forwards the record's geometry"`
Expected: FAIL — `selectRecord` doesn't forward `r.geometry` yet.

- [ ] **Step 7: Implement in `data.tsx`**

Update the list widget's `selectRecord` (currently lines 54-59):

```typescript
      function selectRecord(r: DataRecord) {
        ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r);
        const datasetId = ctx.data?.datasetId;
        const pkColumn = ctx.data?.pkColumn;
        if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(r.id), String(props.dataSourceId ?? ""), r.geometry);
      }
```

Update the table widget's `selectRecord` (currently lines 187-192) identically:

```typescript
      function selectRecord(r: DataRecord) {
        ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r);
        const datasetId = ctx.data?.datasetId;
        const pkColumn = ctx.data?.pkColumn;
        if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(r.id), String(props.dataSourceId ?? ""), r.geometry);
      }
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/data.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/builder/widgets/data.test.tsx
git commit -m "feat(shell): forward feature geometry to cross-filter on click (SP-14n)"
```

---

## Task 8: Shell — `useDatasets()` + `AnalyticsContextIndicator` shows propagated links

**Files:**
- Modify: `shell/src/builder/DataContext.tsx:1-11,84-97` (export `DatasetsContext`, provide it, add `useDatasets()`)
- Modify: `shell/src/builder/AppRenderer.tsx:184,190-200` (move the indicator inside `<DataProvider>`)
- Modify: `shell/src/builder/AnalyticsContextIndicator.tsx` (consume `useDatasets()`, render propagated links)
- Test: `shell/src/builder/AnalyticsContextIndicator.test.tsx` (append)

**Interfaces:**
- Produces: `useDatasets(): Record<string, DatasetConfig>` — mirrors `useDataStates()`'s pattern in the same file. `AnalyticsContextIndicator` unchanged for consumers who don't care about links (default empty datasets map → no visual change); with a `DatasetsContext.Provider` supplying datasets that declare `crossFilterLinks`, each active chip additionally shows the datasets it propagates to.

- [ ] **Step 1: Write the failing indicator test**

Append to `shell/src/builder/AnalyticsContextIndicator.test.tsx`. Add the import at the top:

```typescript
import type { DatasetConfig } from "../api/types";
import { DatasetsContext } from "./DataContext";
```

Then the test:

```typescript
test("shows the dataset(s) a cross-filter propagates to via a declared link", async () => {
  const datasets: Record<string, DatasetConfig> = {
    ds1: {
      source: "collection", collectionId: "communes", columns: {},
      crossFilterLinks: [{ targetDatasetId: "ds2", mode: "attribute", sourceField: "region", targetField: "region" }],
    },
  };
  render(
    <DatasetsContext.Provider value={datasets}>
      <AnalyticsContextProvider interactions="auto">
        <Controls />
        <AnalyticsContextIndicator />
      </AnalyticsContextProvider>
    </DatasetsContext.Provider>,
  );
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  expect(screen.getByText(/→ ds2/)).toBeInTheDocument();
});

test("shows no propagation arrow when the dataset declares no matching link", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  expect(screen.queryByText(/→/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContextIndicator.test.tsx`
Expected: FAIL — `DataContext.tsx` exports no `DatasetsContext` yet (import error), and the indicator never renders a "→" arrow.

- [ ] **Step 3: Implement `useDatasets()` in `DataContext.tsx`**

Export the context and provide it (currently lines 11 and 84-97):

```typescript
export const DatasetsContext = createContext<Record<string, DatasetConfig>>({});
const DataStatesContext = createContext<Record<string, DataSourceState>>({});
const SetFilterContext = createContext<SetFilter>(() => {});
```

At the end of `DataProvider`'s return (currently lines 84-89), wrap the existing providers with it:

```typescript
  return (
    <SetFilterContext.Provider value={setFilter}>
      <DatasetsContext.Provider value={datasets}>
        <DataStatesContext.Provider value={states}>{children}</DataStatesContext.Provider>
      </DatasetsContext.Provider>
    </SetFilterContext.Provider>
  );
}

export function useDataStates(): Record<string, DataSourceState> {
  return useContext(DataStatesContext);
}

export function useDatasets(): Record<string, DatasetConfig> {
  return useContext(DatasetsContext);
}

export function useSetFilter(): SetFilter {
  return useContext(SetFilterContext);
}
```

- [ ] **Step 4: Move the indicator inside `<DataProvider>` in `AppRenderer.tsx`**

Remove the indicator from its current position (line 184, sibling before `<ExplorerDrawer />`):

```typescript
                <ExplorerDrawer />
```

And render it as the first child of `<DataProvider>` instead (currently lines 190-200):

```typescript
                <DataProvider sources={config.dataSources}>
                  {analyticsUiEnabled && <AnalyticsContextIndicator />}
                  <GridCanvas
                    items={activeLayout.items}
                    breakpoint={bp}
                    editable={editable}
                    selectedId={selectedId}
                    onSelect={(id) => onSelect?.(id)}
                    onMoveItem={handleMove}
                    renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} breakpoint={bp} />}
                  />
                </DataProvider>
```

(`DataProvider` renders no DOM element of its own — it's a bare context wrapper — so the indicator's position in the rendered DOM relative to `ExplorerDrawer`/`GridCanvas` is unchanged; only its position in React's component tree moves, which is what makes `useDatasets()` resolve correctly.)

- [ ] **Step 5: Implement in `AnalyticsContextIndicator.tsx`**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { useAnalyticsContext, useClearCrossFilter, useSetExtent, useSetTimeRange, type CrossFilterValue } from "./AnalyticsContext";
import { useDatasets } from "./DataContext";

const chipCls = "flex items-center gap-1 rounded-full border border-[var(--gs-color-border)] px-2 py-1";

function formatCrossFilterValue(value: CrossFilterValue): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return `${value.from} → ${value.to}`;
  return value;
}

export function AnalyticsContextIndicator() {
  const ctx = useAnalyticsContext();
  const datasets = useDatasets();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const clearCrossFilter = useClearCrossFilter();

  const crossFilterIds = Object.keys(ctx.crossFilter).filter((id) => ctx.crossFilter[id]);
  const chipCount = (ctx.timeRange ? 1 : 0) + (ctx.extent ? 1 : 0) + crossFilterIds.length;
  if (chipCount === 0) return null;

  function clearAll() {
    setTimeRange(null);
    setExtent(null);
    crossFilterIds.forEach((id) => clearCrossFilter(id));
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] p-2 text-xs text-[var(--gs-color-text)]">
      {ctx.timeRange && (
        <span className={chipCls}>
          Période : {ctx.timeRange.from} → {ctx.timeRange.to}
          <button type="button" aria-label="Effacer la période" onClick={() => setTimeRange(null)}>×</button>
        </span>
      )}
      {ctx.extent && (
        <span className={chipCls}>
          Emprise carte active
          <button type="button" aria-label="Effacer l'emprise" onClick={() => setExtent(null)}>×</button>
        </span>
      )}
      {crossFilterIds.map((datasetId) => {
        const entry = ctx.crossFilter[datasetId]!;
        const propagatesTo = (datasets[datasetId]?.crossFilterLinks ?? [])
          .filter((link) => (link.mode === "attribute" ? link.sourceField === entry.field : entry.geometry !== undefined))
          .map((link) => link.targetDatasetId);
        return (
          <span key={datasetId} className={chipCls}>
            {entry.field} : {formatCrossFilterValue(entry.value)}
            {propagatesTo.length > 0 && (
              <span className="text-[var(--gs-color-muted)]"> → {propagatesTo.join(", ")}</span>
            )}
            <button type="button" aria-label={`Effacer le filtre ${entry.field}`} onClick={() => clearCrossFilter(datasetId)}>×</button>
          </span>
        );
      })}
      {chipCount >= 2 && (
        <button type="button" className="ml-auto underline" onClick={clearAll}>Tout effacer</button>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AnalyticsContextIndicator.test.tsx`
Expected: PASS (all tests, including the 2 new ones — `useDatasets()` defaults to `{}` when no `DatasetsContext.Provider` is mounted, so every pre-existing test in this file, none of which wraps one, is unaffected).

- [ ] **Step 7: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 8: Run the E2E suite to confirm the indicator's move doesn't break scenario 8/9**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- analytics-context.spec.ts`
Expected: all scenarios in this file still pass, including scenario 8 ("the context indicator shows chips...") and scenario 9 (manual non-regression) — the indicator's DOM position relative to other elements is unchanged (Step 4's comment).

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/DataContext.tsx shell/src/builder/AppRenderer.tsx shell/src/builder/AnalyticsContextIndicator.tsx shell/src/builder/AnalyticsContextIndicator.test.tsx
git commit -m "feat(shell): indicator shows datasets a cross-filter propagates to (SP-14n)"
```

---

## Task 9: Shell — `CrossFilterLinkEditor` + `DatasetEditPage` wiring

**Files:**
- Create: `shell/src/builder/CrossFilterLinkEditor.tsx`
- Test: `shell/src/builder/CrossFilterLinkEditor.test.tsx` (new)
- Modify: `shell/src/pages/DatasetEditPage.tsx:1-9,93-114` (add the links section)
- Test: `shell/src/pages/DatasetEditPage.test.tsx` (append)

**Interfaces:**
- Consumes: `useItems` (`shell/src/api/hooks.ts:8`), `useDatasetConfig` (`:230`), `client.getCollectionSchema` (`shell/src/api/ItemClientProvider` via `useItemClient`).
- Produces: `CrossFilterLinkEditor({ link, sourceFields, targetOptions, onChange, onRemove })` — one link's full UI (target dataset, mode, field pickers or precision picker). `DatasetEditPage` renders one per `draft.crossFilterLinks` entry plus an "Ajouter un lien" button, and includes the array in the payload passed to `save.mutate(draft)`.

- [ ] **Step 1: Write the failing `CrossFilterLinkEditor` tests**

Create `shell/src/builder/CrossFilterLinkEditor.test.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionSchema, DatasetConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CrossFilterLinkEditor } from "./CrossFilterLinkEditor";

const incidentsDataset: DatasetConfig = { source: "collection", collectionId: "incidents", columns: {} };
const incidentsSchema: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [{ name: "titre", type: "string" }, { name: "commune", type: "string" }],
};

function renderEditor(client: Partial<ItemClient>, props: Partial<Parameters<typeof CrossFilterLinkEditor>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChange = vi.fn();
  const onRemove = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <CrossFilterLinkEditor
          link={{ targetDatasetId: "", mode: "attribute", sourceField: "", targetField: "" }}
          sourceFields={["region", "commune"]}
          targetOptions={[{ pk: "ds-2", title: "Incidents" }]}
          onChange={onChange}
          onRemove={onRemove}
          {...props}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange, onRemove };
}

test("changing the target dataset calls onChange with the updated link", async () => {
  const { onChange } = renderEditor({});
  await userEvent.selectOptions(screen.getByLabelText("Dataset cible"), "ds-2");
  expect(onChange).toHaveBeenCalledWith({ targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" });
});

test("switching to spatial mode resets the link to a bbox-precision spatial link", async () => {
  const { onChange } = renderEditor({}, { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } });
  await userEvent.selectOptions(screen.getByLabelText("Mode du lien"), "spatial");
  expect(onChange).toHaveBeenCalledWith({ targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" });
});

test("attribute mode offers source fields and the target dataset's own fields", async () => {
  renderEditor(
    { getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset), getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema) },
    { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } },
  );
  expect(screen.getByLabelText("Champ source")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("Champ cible")).toBeInTheDocument());
  expect(screen.getByRole("option", { name: "commune" })).toBeInTheDocument();
});

test("spatial mode shows a precision select only when the target collection has geometry", async () => {
  renderEditor(
    { getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset), getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema) },
    { link: { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" } },
  );
  await waitFor(() => expect(screen.getByLabelText("Précision spatiale du lien")).toBeInTheDocument());
});

test("spatial mode hides the precision select when the target collection has no geometry", async () => {
  renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue({ ...incidentsSchema, geometry: null }),
    },
    { link: { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" } },
  );
  await screen.findByLabelText("Dataset cible");
  expect(screen.queryByLabelText("Précision spatiale du lien")).not.toBeInTheDocument();
});

test("clicking remove calls onRemove", async () => {
  const { onRemove } = renderEditor({});
  await userEvent.click(screen.getByRole("button", { name: "Supprimer le lien" }));
  expect(onRemove).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/CrossFilterLinkEditor.test.tsx`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement `CrossFilterLinkEditor.tsx`**

Create `shell/src/builder/CrossFilterLinkEditor.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink } from "../api/types";

export function CrossFilterLinkEditor({
  link, sourceFields, targetOptions, onChange, onRemove,
}: {
  link: CrossFilterLink;
  sourceFields: string[];
  targetOptions: { pk: string; title: string }[];
  onChange: (next: CrossFilterLink) => void;
  onRemove: () => void;
}) {
  const client = useItemClient();
  const targetConfigQuery = useDatasetConfig(link.targetDatasetId, { enabled: Boolean(link.targetDatasetId) });
  const targetCollectionId =
    targetConfigQuery.data && targetConfigQuery.data.source === "collection" ? targetConfigQuery.data.collectionId : undefined;
  const targetSchemaQuery = useQuery({
    queryKey: ["collection-schema", targetCollectionId],
    queryFn: () => client.getCollectionSchema(targetCollectionId!),
    enabled: Boolean(targetCollectionId),
  });
  const targetHasGeometry = Boolean(targetSchemaQuery.data?.geometry);
  const targetFields = targetSchemaQuery.data?.fields.map((f) => f.name) ?? [];

  function changeMode(mode: "attribute" | "spatial") {
    onChange(
      mode === "attribute"
        ? { targetDatasetId: link.targetDatasetId, mode: "attribute", sourceField: "", targetField: "" }
        : { targetDatasetId: link.targetDatasetId, mode: "spatial", precision: "bbox" },
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-slate-200 p-2 text-xs">
      <label className="flex flex-col gap-1">
        Dataset cible
        <select
          aria-label="Dataset cible"
          className="h-8 rounded border border-slate-300 px-2"
          value={link.targetDatasetId}
          onChange={(e) => onChange({ ...link, targetDatasetId: e.target.value })}
        >
          <option value="">— choisir —</option>
          {targetOptions.map((d) => <option key={d.pk} value={d.pk}>{d.title}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Mode du lien
        <select
          aria-label="Mode du lien"
          className="h-8 rounded border border-slate-300 px-2"
          value={link.mode}
          onChange={(e) => changeMode(e.target.value as "attribute" | "spatial")}
        >
          <option value="attribute">Attribut partagé</option>
          <option value="spatial">Spatial</option>
        </select>
      </label>
      {link.mode === "attribute" ? (
        <>
          <label className="flex flex-col gap-1">
            Champ source
            <select
              aria-label="Champ source"
              className="h-8 rounded border border-slate-300 px-2"
              value={link.sourceField}
              onChange={(e) => onChange({ ...link, sourceField: e.target.value })}
            >
              <option value="">— choisir —</option>
              {sourceFields.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Champ cible
            <select
              aria-label="Champ cible"
              className="h-8 rounded border border-slate-300 px-2"
              value={link.targetField}
              onChange={(e) => onChange({ ...link, targetField: e.target.value })}
            >
              <option value="">— choisir —</option>
              {targetFields.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
        </>
      ) : (
        targetHasGeometry && (
          <label className="flex flex-col gap-1">
            Précision spatiale du lien
            <select
              aria-label="Précision spatiale du lien"
              className="h-8 rounded border border-slate-300 px-2"
              value={link.precision}
              onChange={(e) => onChange({ ...link, precision: e.target.value as "bbox" | "exact" })}
            >
              <option value="bbox">Emprise (rapide)</option>
              <option value="exact">Intersection exacte</option>
            </select>
          </label>
        )
      )}
      <button type="button" className="self-start text-red-600 underline" onClick={onRemove}>
        Supprimer le lien
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/CrossFilterLinkEditor.test.tsx`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Write the failing `DatasetEditPage` tests**

Append to `shell/src/pages/DatasetEditPage.test.tsx`:

```typescript
test("adding a cross-filter link and saving includes it in the saved payload", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [{ pk: "ds-2", resourceType: "dataset", title: "Incidents", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false }],
      total: 1, page: 1, pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un lien" }));
  await userEvent.selectOptions(screen.getByLabelText("Dataset cible"), "ds-2");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" },
  ]);
});

test("removing a cross-filter link drops it from the draft before saving", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue({
      ...datasetConfig,
      crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "attribute" as const, sourceField: "nom", targetField: "nom" }],
    }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [{ pk: "ds-2", resourceType: "dataset", title: "Incidents", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false }],
      total: 1, page: 1, pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer le lien" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([]);
});
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: FAIL — `DatasetEditPage` has no "Ajouter un lien" button yet.

- [ ] **Step 7: Wire it into `DatasetEditPage.tsx`**

Extend the imports (currently lines 1-9):

```typescript
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig, useItem, useItems, useSaveDataset, useUpdateItem } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink, DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { MetadataForm } from "../ui/MetadataForm";
import { Button } from "../ui/button";
import { CrossFilterLinkEditor } from "../builder/CrossFilterLinkEditor";
```

Add the target-dataset list query and link-editing helpers, right after `setColumn` (currently around line 40):

```typescript
  const otherDatasetsQuery = useItems({ type: "dataset", pageSize: 100 });
  const targetOptions = (otherDatasetsQuery.data?.items ?? [])
    .filter((d) => d.pk !== pk)
    .map((d) => ({ pk: d.pk, title: d.title }));

  function addCrossFilterLink() {
    setDraft((d) =>
      d ? { ...d, crossFilterLinks: [...(d.crossFilterLinks ?? []), { targetDatasetId: "", mode: "attribute" as const, sourceField: "", targetField: "" }] } : d,
    );
  }
  function updateCrossFilterLink(index: number, next: CrossFilterLink) {
    setDraft((d) => {
      if (!d) return d;
      const links = [...(d.crossFilterLinks ?? [])];
      links[index] = next;
      return { ...d, crossFilterLinks: links };
    });
  }
  function removeCrossFilterLink(index: number) {
    setDraft((d) => {
      if (!d) return d;
      const links = (d.crossFilterLinks ?? []).filter((_, i) => i !== index);
      return { ...d, crossFilterLinks: links };
    });
  }
```

Add the section in the JSX, right after the "Réagir au déplacement de la carte" `<label>` (currently lines 105-113, before the closing `</div>` at line 114):

```typescript
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs font-medium text-slate-500">Liens cross-filter</p>
          {(draft.crossFilterLinks ?? []).map((link, i) => (
            <CrossFilterLinkEditor
              key={i}
              link={link}
              sourceFields={merged.map((f) => f.name)}
              targetOptions={targetOptions}
              onChange={(next) => updateCrossFilterLink(i, next)}
              onRemove={() => removeCrossFilterLink(i)}
            />
          ))}
          <button type="button" className="self-start rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100" onClick={addCrossFilterLink}>
            Ajouter un lien
          </button>
        </div>
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: PASS (all tests in the file, including the 2 new ones).

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/CrossFilterLinkEditor.tsx shell/src/builder/CrossFilterLinkEditor.test.tsx shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx
git commit -m "feat(shell): author cross-filter links in DatasetEditPage (SP-14n)"
```

---

## Task 10: E2E — cross-filter inter-datasets scenario

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts` (append a new scenario, reusing `createApp`/`addFeaturesSource`/`promoteLastSource`)

**Interfaces:**
- Consumes: the real builder UI end-to-end — two datasets ("Communes", polygons; "Incidents", points), a cross-filter link authored via `DatasetEditPage` (Task 9), an app with a Table (communes) and an Indicateur/KPI (statistics, incidents), exercising the bbox-mode path that's fully wired (Tasks 4/5/7; the `exact` core capability from Tasks 1-2 exists but this plan's shell wiring only exercises `bbox`, per the Global Constraints note).

- [ ] **Step 1: Write the E2E scenario**

Append to `shell/e2e/analytics-context.spec.ts`:

```typescript
// -------------------------------------------------------------------------
// Scénario 15 (SP-14n) — cross-filter inter-datasets : un lien spatial/bbox
// déclaré sur le dataset "Communes" vers "Incidents" fait qu'un clic sur une
// commune (Table) filtre l'indicateur (statistics) du dataset "Incidents"
// par le bbox de sa géométrie — sans lien direct entre les deux sources.
// -------------------------------------------------------------------------
test("a spatial cross-filter link propagates a bbox from one dataset's Table click to another dataset's KPI", async ({ page }) => {
  await mockCore(page);

  let nextDatasetId = 0;
  const savedDatasets = new Map<string, Record<string, unknown>>();
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body.config?.kind !== "dataset") return route.fallback();
    nextDatasetId += 1;
    const itemId = `dataset-${nextDatasetId}`;
    savedDatasets.set(itemId, body.config.dataset);
    await route.fulfill({ status: 201, json: { id: `cfg-${itemId}`, kind: "dataset", itemId } });
  });
  await page.route("**/configs/by-item/dataset-*", async (route) => {
    const itemId = new URL(route.request().url()).pathname.split("/").pop()!;
    if (route.request().method() === "PUT") {
      savedDatasets.set(itemId, (await route.request().postDataJSON()).dataset);
      await route.fulfill({ json: { id: `cfg-${itemId}`, itemId, kind: "dataset", dataset: savedDatasets.get(itemId) } });
      return;
    }
    await route.fulfill({
      json: { id: `cfg-${itemId}`, itemId, kind: "dataset", config: { kind: "dataset", dataset: savedDatasets.get(itemId) } },
    });
  });
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "dataset") return route.fallback();
    const items = [...savedDatasets.keys()].map((id) => ({
      pk: id, resourceType: "dataset", title: id === "dataset-1" ? "Incidents partagés" : "Communes partagées",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: `cfg-${id}`, isPublished: false,
    }));
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 100 } });
  });
  await page.route("https://core.test/items/dataset-*", async (route) => {
    const id = route.request().url().split("/").pop()!;
    await route.fulfill({
      json: {
        pk: id, resourceType: "dataset", title: id === "dataset-1" ? "Incidents partagés" : "Communes partagées",
        abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: `cfg-${id}`, isPublished: false, keywords: [],
      },
    });
  });

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          { id: "incidents-pts", title: "Incidents", description: "", tableName: "incidents_pts", isPublic: true, editable: true, geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 5, owner: "mockuser" },
          { id: "communes", title: "Communes", description: "", tableName: "communes", isPublic: true, editable: true, geometryType: "Polygon", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 1, owner: "mockuser" },
        ],
      },
    });
  });
  await page.route("**/collections/incidents-pts/schema", async (route) => {
    await route.fulfill({ json: { collection: "incidents-pts", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 }, fields: [{ name: "titre", type: "string" }] } });
  });
  await page.route("**/collections/communes/schema", async (route) => {
    await route.fulfill({ json: { collection: "communes", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 }, fields: [{ name: "nom", type: "string" }] } });
  });
  await page.route("**/collections/communes/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [{
          id: 1, properties: { nom: "Brive" },
          geometry: { type: "Polygon", coordinates: [[[1.0, 45.0], [2.0, 45.0], [2.0, 46.0], [1.0, 46.0], [1.0, 45.0]]] },
        }],
      },
    });
  });
  // L'indicateur (statistics) sur "incidents-pts" : 5 sans filtre, 2 dès que
  // le bbox posé par le lien correspond à l'emprise de Brive.
  await page.route("**/collections/incidents-pts/aggregate", async (route) => {
    const body = await route.request().postDataJSON();
    const count = body.bbox ? 2 : 5;
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: count }] } });
  });

  // 1. Créer le dataset "Incidents" en premier (cible du lien, doit déjà
  //    exister pour apparaître dans le sélecteur de dataset cible).
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  let dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("incidents-pts");
  await dialog.getByLabel("Titre").fill("Incidents partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);

  // 2. Créer le dataset "Communes" puis lui déclarer un lien spatial/bbox
  //    vers "Incidents".
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("communes");
  await dialog.getByLabel("Titre").fill("Communes partagées");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-2\/edit$/);

  await page.getByRole("button", { name: "Ajouter un lien" }).click();
  await page.getByLabel("Dataset cible").selectOption("dataset-1");
  await page.getByLabel("Mode du lien").selectOption("spatial");
  await expect(page.getByLabel("Précision spatiale du lien")).toHaveValue("bbox");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();
  await expect.poll(() => savedDatasets.get("dataset-2")).toMatchObject({
    crossFilterLinks: [{ targetDatasetId: "dataset-1", mode: "spatial", precision: "bbox" }],
  });

  // 3. App : Table sur "Communes" (source 1), Indicateur (statistics) sur
  //    "Incidents" (source 2).
  await createApp(page, "Cross-filter inter-datasets");
  await addFeaturesSource(page, "communes");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "incidents-pts");
  await promoteLastSource(page, 2);
  await page.getByLabel(/Type de la source/).last().selectOption("statistics");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 4. Runtime : la KPI montre 5 (non filtrée) ; cliquer la ligne "Brive" de
  //    la Table communes filtre la KPI incidents à 2 via bbox propagé.
  await page.goto("/apps/9");
  await expect(page.getByText("5")).toBeVisible();

  const filteredReq = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().includes("/collections/incidents-pts/aggregate") && (r.postData() ?? "").includes("bbox"),
  );
  await page.getByRole("cell", { name: "Brive" }).click();
  await filteredReq;
  await expect(page.getByText("2")).toBeVisible();
});
```

- [ ] **Step 2: Run the new scenario to verify it fails first**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- analytics-context.spec.ts -g "spatial cross-filter link"`
Expected: FAIL at some point before Tasks 1-9 land (e.g. "Ajouter un lien" button not found, or the KPI never drops to 2) — confirms the test actually exercises the new behavior rather than trivially passing.

- [ ] **Step 3: Run it again after Tasks 1-9 are complete**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- analytics-context.spec.ts -g "spatial cross-filter link"`
Expected: PASS.

- [ ] **Step 4: Run the full E2E suite for this file**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- analytics-context.spec.ts`
Expected: all scenarios in the file pass (the 14 pre-existing ones + the new one), no regressions.

- [ ] **Step 5: Run the full E2E suite**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: all 18+1 specs green (per `CLAUDE.md`'s "18 specs" baseline, now 18 files with one additional scenario in an existing file — no new spec file).

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(e2e): exercise a spatial cross-filter link across two datasets (SP-14n)"
```

---

## Post-implementation follow-up (not part of this plan's tasks)

Once Task 10 is merged, SP-14n is the last unblocked item of SP-14's roadmap content — only the visual query builder remains, blocked on SP-15. Update `docs/vision/2026-07-04-feuille-de-route-geostudio.md` and `CLAUDE.md`'s "Fait"/"À venir" sections accordingly (mark SP-14 as functionally complete modulo the SP-15-blocked piece, note jalon M11's status) as a separate documentation commit, per the workflow's own convention (see how SP-14l/SP-14m's roadmap entries were added in prior commits) — do not fold that documentation update into any of the 10 code tasks above.
