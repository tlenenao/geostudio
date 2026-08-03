# SP-14b — Contexte analytique global & cross-filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widgets in a GeoStudio app react to each other and to a global time/extent context (cross-filter on click, map-extent refetch, a date-range control) without manual wiring, and the resulting state round-trips through the URL — gated behind an additive `interactions: "auto"` app flag so every existing app/E2E spec stays byte-identical.

**Architecture:** A new `AnalyticsContextProvider` (shell/src/builder/AnalyticsContext.tsx) holds `{timeRange, extent, crossFilter}` and exposes setter hooks that are silent no-ops unless `config.interactions === "auto"`. `DataContext.tsx`'s per-DataSource query gains an extra layer — `derivePatch(source, ctx, datasets)` — that turns the global context into query filters (`field__gte`/`field__lte`/`field__in`/`bbox`) for datasource-backed sources only. Three widgets (chart, table/list, map) call the context's setters on click/move; a new `dateRangeFilter` widget drives `timeRange` directly. The core gains the `__gte`/`__lte`/`__in` filter-key suffixes in both `features/repository.py` and `analytics/aggregate.py` to serve those patched queries. The runtime route encodes the whole context as one opaque base64url query param, debounced and written with `replace: true`.

**Tech Stack:** FastAPI/SQLAlchemy/Pydantic (core), React/TypeScript/@tanstack/react-query/react-router-dom v6/cel-js (shell), Vitest + Testing Library (unit), Playwright (E2E), pytest (core, `postgis` marker requires `CORE_TEST_DATABASE_URL`).

## Global Constraints

- Additive only: `AppConfig.interactions` absent behaves exactly as `"manual"` (today's behavior, unchanged); only a **newly created** app defaults to `"auto"` (insertion point: `itemClient.ts` `createConfigItem`, same spot as the existing `navigationMode` default).
- All `AnalyticsContextProvider` setters (`setTimeRange`/`setExtent`/`setCrossFilter`) are **silent no-ops** when `interactions !== "auto"` — no `if` branch may be added inside any widget to guard this; the provider owns the guard.
- No strict server-side validation of `DatasetPayload.timeField` against the collection's real schema — same posture as the existing `columns` field (SP-14a §3). A dangling `timeField` fails at real-query time (HTTP 400/422), not at save time.
- v1 cross-filter: **one active value per dataset**; a second click on the same `(field, value)` toggles it off (delete), a different value replaces it. No multi-value accumulation.
- The widget that emitted a cross-filter click is never filtered by its own click, but gets **no dedicated "selected" visual style** — out of scope.
- Cross-filter only applies between widgets bound to the **same `datasetId`** — never across different datasets.
- The map-extent setter debounces internally in the provider (~500 ms, exported as `EXTENT_DEBOUNCE_MS`), not in the widget. The runtime page's URL write debounces on the same constant.
- URL sync is a single opaque query param `ctx=<base64url(JSON)>` on the existing `/apps/:pk/:pageId?` route only, written with `setSearchParams(..., { replace: true })` — never `push` — and only when `mode === "runtime"` (i.e. only from `AppRuntimePage`, not from `SitePublicPage`/`DatasetPage`/`PublicItemPage`, which are out of this plan's scope per spec §6).
- All SQL stays parameterized (SQLAlchemy `:params` in `repository.py`, DuckDB `?` positional params in `aggregate.py`) — the new `__gte`/`__lte`/`__in` suffixes must never be interpolated into SQL text.
- Every one of the 18 existing E2E specs must stay green **without modification**.
- Explicitly out of scope for this plan (do not build): typed select/slider filter widgets (SP-14c), a "view entities" drill panel (SP-14d), cross-**dataset** cross-filter, multi-value (ctrl-click) cross-filter, a highlighted/"selected" visual style for the origin widget, server-persisted named bookmarks, visual query builder / SQL Lab / `arcgis` dataset source / analytics MCP tools (later SP-14 sub-parts).

---

### Task 1: Core — `interactions` on `BuilderConfig`, `timeField`/`reactsToExtent` on `DatasetPayload`, OpenAPI regen

**Files:**
- Modify: `core/app/configs/schemas.py:95-115`
- Modify: `core/openapi.json` (regenerated, not hand-edited)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)
- Test: `core/tests/test_dataset_config_schema.py`
- Test: `core/tests/test_schemas.py`

**Interfaces:**
- Produces: `BuilderConfig.interactions: Literal["auto", "manual"] | None` (default `None`), `DatasetPayload.timeField: str | None` (default `None`), `DatasetPayload.reactsToExtent: bool` (default `False`). Both round-trip through `ConfigRead`/`model_dump(by_alias=True)` automatically (no route code touches these — same generic pass-through as `navigationMode`, confirmed by reading `core/app/configs/repository.py:26-31` and `core/app/configs/routes.py`).

- [ ] **Step 1: Write the failing core tests**

Append to `core/tests/test_dataset_config_schema.py`:

```python
def test_dataset_config_time_field_and_reacts_to_extent_optional():
    body = _dataset_body()
    body["dataset"]["timeField"] = "date_releve"
    body["dataset"]["reactsToExtent"] = True
    config = BuilderConfig.model_validate(body)
    assert config.dataset.timeField == "date_releve"
    assert config.dataset.reactsToExtent is True


def test_dataset_config_time_field_and_reacts_to_extent_default():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.dataset.timeField is None
    assert config.dataset.reactsToExtent is False
```

Append to `core/tests/test_schemas.py` (near `test_navigation_mode_*`, using the existing `_valid_payload` helper):

```python
def test_interactions_round_trips():
    payload = _valid_payload("app")
    payload["interactions"] = "auto"
    config = BuilderConfig.model_validate(payload)
    assert config.interactions == "auto"
    dumped = config.model_dump(by_alias=True)
    assert dumped["interactions"] == "auto"


def test_interactions_defaults_to_none():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.interactions is None


def test_interactions_rejects_unknown_value():
    payload = _valid_payload("app")
    payload["interactions"] = "sometimes"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py tests/test_schemas.py -v -k "time_field or reacts_to_extent or interactions"`
Expected: FAIL — `AttributeError`/`KeyError`-style failures (fields don't exist yet on `DatasetPayload`/`BuilderConfig`).

- [ ] **Step 3: Add the fields**

In `core/app/configs/schemas.py`, replace:

```python
class DatasetPayload(BaseModel):
    source: Literal["collection"]  # seul type supporté en SP-14a
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
```

with:

```python
class DatasetPayload(BaseModel):
    source: Literal["collection"]  # seul type supporté en SP-14a
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte (SP-14b)
```

And in `BuilderConfig`, replace:

```python
    navigationMode: Literal["tabs", "story"] = "tabs"
    variables: list[Variable] = Field(default_factory=list)
```

with:

```python
    navigationMode: Literal["tabs", "story"] = "tabs"
    interactions: Literal["auto", "manual"] | None = None
    variables: list[Variable] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py tests/test_schemas.py -v -k "time_field or reacts_to_extent or interactions"`
Expected: PASS

- [ ] **Step 5: Regenerate the OpenAPI schema and shell types**

Run:
```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` gains `interactions`/`timeField`/`reactsToExtent` entries under `BuilderConfig`/`DatasetPayload`; `shell/src/api/generated/core-schema.d.ts` picks them up. This mirrors commit `14401ae` (`chore(shell,core): régénérer les types OpenAPI (kind=dataset)`) — keeps the `api-types-drift` CI job green.

- [ ] **Step 6: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: PASS (previous count + 6 new tests; unrelated `postgis`-marked tests still skip without `CORE_TEST_DATABASE_URL`).

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/openapi.json shell/src/api/generated/core-schema.d.ts core/tests/test_dataset_config_schema.py core/tests/test_schemas.py
git commit -m "feat(core): interactions sur BuilderConfig, timeField/reactsToExtent sur DatasetPayload (SP-14b)"
```

---

### Task 2: Core — `__gte`/`__lte`/`__in` filter suffixes in `features/repository.py`

**Files:**
- Modify: `core/app/features/repository.py:54-73` (`_where`)
- Test: `core/tests/test_features_repository.py`

**Interfaces:**
- Produces: `_where(session, info, bbox, filters)` now accepts filter keys of the form `field`, `field__gte`, `field__lte`, `field__in` (comma-separated value). Public signature and `FilterError` contract unchanged — `select_features`'s callers (`core/app/features/routes.py`) need no change.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_features_repository.py` (uses the existing `pg_incidents` fixture — `t_feat` has `id`, `titre`, `nb integer`):

```python
def test_gte_lte_filters_narrow_by_range(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, filters={"nb__gte": "2"})
        assert [f["id"] for f in page.features] == [2]
        page = select_features(session, info, limit=10, offset=0, filters={"nb__lte": "1"})
        assert [f["id"] for f in page.features] == [1]
        page = select_features(session, info, limit=10, offset=0,
                               filters={"nb__gte": "1", "nb__lte": "1"})
        assert [f["id"] for f in page.features] == [1]


def test_in_filter_matches_any_listed_value(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, filters={"titre__in": "a,b"})
        assert sorted(f["id"] for f in page.features) == [1, 2]
        page = select_features(session, info, limit=10, offset=0, filters={"titre__in": "a"})
        assert [f["id"] for f in page.features] == [1]


def test_suffixed_filter_on_unknown_column_still_raises_filter_error(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"inconnu__gte": "1"})


def test_gte_on_unparseable_value_raises_filter_error(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info, limit=10, offset=0, filters={"nb__gte": "pas-un-nombre"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest tests/test_features_repository.py -v -k "gte or lte or in_filter or suffixed"`
(Requires a real Postgres — e.g. `docker compose up -d postgis` and export the matching `CORE_TEST_DATABASE_URL`; without it these tests are skipped, not failed — confirm they're collected and skipped if docker isn't available, then proceed to the implementation and re-verify with docker up if possible.)
Expected: FAIL — `nb__gte`/`titre__in`/etc. are treated as literal unknown column names today (raise `FilterError` unconditionally, including the range test that expects a narrowed, non-empty page).

- [ ] **Step 3: Implement the suffix parsing and per-operator SQL**

In `core/app/features/repository.py`, replace `_where`:

```python
def _where(session: Session, info: TableInfo, bbox, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (name, raw) in enumerate(sorted(filters.items())):
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            clauses.append(f"{quote_ident(session, name)} = :f{i}")
            params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(f"{g} && ST_Transform(ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, 4326), :bsrid)")
        params.update({"bx0": bbox[0], "by0": bbox[1], "bx1": bbox[2],
                       "by1": bbox[3], "bsrid": info.srid or 4326})
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params
```

with:

```python
_RANGE_OPS = {"__gte": ">=", "__lte": "<="}


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None


def _where(session: Session, info: TableInfo, bbox, filters):
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
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest tests/test_features_repository.py -v`
Expected: PASS (all tests in the file, old and new).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/features/repository.py core/tests/test_features_repository.py
git commit -m "feat(core): opérateurs de filtre __gte/__lte/__in sur les features (SP-14b)"
```

---

### Task 3: Core — `__gte`/`__lte`/`__in` filter suffixes in `analytics/aggregate.py`

**Files:**
- Modify: `core/app/analytics/aggregate.py:56-71` (`_validate_fields`), `:101-117` (`_build_where`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `_build_where` accepts the same `field`/`field__gte`/`field__lte`/`field__in` keys in `AggregateRequestBody.filters`. `_validate_fields` validates the **stripped** column name (unsuffixed) against the table's known columns, so an unsuffixed unknown-column error stays byte-identical.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_analytics_aggregate.py`:

```python
def test_gte_lte_filters_narrow_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 20, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop",
                                    filters={"annee__gte": "2026"})
    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )
    assert rows == [{"region": "Nord", "value": 20}]


def test_in_filter_matches_any_listed_value(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1),
        _row(3, "Est", "2025", 3, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop",
                                    filters={"region__in": "Nord,Sud"})
    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10}, {"region": "Sud", "value": 5},
    ]


def test_suffixed_filter_on_unknown_field_raises_with_stripped_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="region", filters={"inconnu__gte": "1"})
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert "inconnu" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v -k "gte or in_filter or suffixed"`
Expected: FAIL — today `annee__gte`/`region__in` are unknown fields (raise `UnknownAggregateField`), not comparisons.

- [ ] **Step 3: Implement the suffix parsing and per-operator SQL**

In `core/app/analytics/aggregate.py`, add near the top (after `_sql_lit`):

```python
_RANGE_OPS = {"__gte": ">=", "__lte": "<="}


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None
```

Replace the filters loop in `_validate_fields`:

```python
    for name in request.filters:
        check(name, f"filters.{name}")
```

with:

```python
    for raw_name in request.filters:
        field_name, _ = _split_filter_key(raw_name)
        check(field_name, f"filters.{raw_name}")
```

Replace `_build_where`'s filters loop:

```python
def _build_where(request: AggregateRequestBody, table_info) -> tuple[str, list]:
    clauses = []
    params: list = []
    for name, value in request.filters.items():
        clauses.append(f"{_qi(name)} = ?")
        params.append(value)
```

with:

```python
def _build_where(request: AggregateRequestBody, table_info) -> tuple[str, list]:
    clauses = []
    params: list = []
    for raw_name, value in request.filters.items():
        name, suffix = _split_filter_key(raw_name)
        if suffix == "__in":
            values = value.split(",")
            clauses.append(f"{_qi(name)} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        elif suffix in _RANGE_OPS:
            clauses.append(f"{_qi(name)} {_RANGE_OPS[suffix]} ?")
            params.append(value)
        else:
            clauses.append(f"{_qi(name)} = ?")
            params.append(value)
```

(leave the rest of `_build_where` — the `bbox` clause below — untouched).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): opérateurs de filtre __gte/__lte/__in sur l'agrégation DuckDB (SP-14b)"
```

---

### Task 4: Shell — `DatasetConfig`/`AppConfig` types + `itemClient.ts` wiring

**Files:**
- Modify: `shell/src/api/types.ts:204-223` (`DataSource`, `DatasetConfig`), `:354-363` (`AppConfig`)
- Modify: `shell/src/api/itemClient.ts:138-151` (`resolveDataset`/`datasetCache`), `:250-269` (`createConfigItem`), `:483-489` (`createDatasetItem`), `:497-505` (`getDatasetConfig`/`saveDatasetConfig`), `:507-572` (`getAppConfig`/`getPublicAppConfig`/`saveAppConfig`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `DatasetConfig.timeField?: string | null`, `DatasetConfig.reactsToExtent?: boolean`; `DataSource.datasetId` (already exists) unchanged; `AppConfig.interactions?: "auto" | "manual"`. `ItemClient.createConfigItem({kind: "app"|"dashboard", ...})` now seeds `config.interactions = "auto"` in the payload it POSTs. `getDatasetConfig`/`saveDatasetConfig`/`getAppConfig`/`getPublicAppConfig`/`saveAppConfig` all round-trip the new fields.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts` (find the existing `getAppConfig`/`saveAppConfig`/dataset tests to place these alongside; use the file's existing `makeClient()`/`http`/`HttpResponse`/`server` conventions):

```ts
test("createConfigItem defaults interactions to auto for a new app", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "cfg-1", kind: "app", itemId: "1" }, { status: 201 });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "Test", owner: "alice" });
  expect((posted!.config as Record<string, unknown>).interactions).toBe("auto");
});

test("getAppConfig/saveAppConfig round-trip interactions", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/9", () =>
      HttpResponse.json({ config: { kind: "app", layout: { type: "grid", breakpoints: {}, items: [] }, interactions: "auto" } }),
    ),
  );
  const config = await makeClient().getAppConfig("9");
  expect(config.interactions).toBe("auto");

  let putBody: Record<string, unknown> | null = null;
  server.use(
    http.put("https://core.test/configs/by-item/9", async ({ request }) => {
      putBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveAppConfig("9", { ...config, interactions: "manual" });
  expect(putBody!.interactions).toBe("manual");
});

test("getDatasetConfig/saveDatasetConfig round-trip timeField/reactsToExtent", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        config: { dataset: { source: "collection", collectionId: "parcs", columns: {}, timeField: "date_releve", reactsToExtent: true } },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.timeField).toBe("date_releve");
  expect(config.reactsToExtent).toBe(true);

  let putBody: Record<string, unknown> | null = null;
  server.use(
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      putBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveDatasetConfig("ds-1", { ...config, reactsToExtent: false });
  expect((putBody!.dataset as Record<string, unknown>).reactsToExtent).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "interactions|timeField|reactsToExtent"`
Expected: FAIL — `config.interactions`/`config.timeField`/`config.reactsToExtent` are `undefined` (fields don't exist yet, and `createConfigItem` doesn't set a default).

- [ ] **Step 3: Extend the types**

In `shell/src/api/types.ts`, replace:

```ts
export type DatasetConfig = {
  source: "collection";
  collectionId: string;
  columns: Record<string, DatasetColumnMeta>;
};
```

with:

```ts
export type DatasetConfig = {
  source: "collection";
  collectionId: string;
  columns: Record<string, DatasetColumnMeta>;
  timeField?: string | null;
  reactsToExtent?: boolean;
};
```

Replace:

```ts
export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
  navigationMode?: "tabs" | "story";
};
```

with:

```ts
export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
  navigationMode?: "tabs" | "story";
  interactions?: "auto" | "manual"; // absent = "manual"
};
```

- [ ] **Step 4: Wire `itemClient.ts`**

Replace the `datasetCache`/`resolveDataset` block (`shell/src/api/itemClient.ts:138-151`):

```ts
  const datasetCache = new Map<string, { collectionId: string; columns: Record<string, DatasetColumnMeta> }>();

  async function resolveDataset(pk: string): Promise<{ collectionId: string; columns: Record<string, DatasetColumnMeta> }> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: { dataset?: { collectionId: string; columns?: Record<string, DatasetColumnMeta> } | null };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved = { collectionId: dataset.collectionId, columns: dataset.columns ?? {} };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

with:

```ts
  type ResolvedDataset = {
    collectionId: string; columns: Record<string, DatasetColumnMeta>;
    timeField: string | null; reactsToExtent: boolean;
  };
  const datasetCache = new Map<string, ResolvedDataset>();

  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: {
        dataset?: {
          collectionId: string; columns?: Record<string, DatasetColumnMeta>;
          timeField?: string | null; reactsToExtent?: boolean;
        } | null;
      };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      collectionId: dataset.collectionId, columns: dataset.columns ?? {},
      timeField: dataset.timeField ?? null, reactsToExtent: dataset.reactsToExtent ?? false,
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

In `createConfigItem` (`:250-269`), inside the `config` object literal, add the `interactions` field right after `navigationMode`:

```ts
        navigationMode: template?.navigationMode ?? "tabs",
        interactions: "auto",
```

In `createDatasetItem` (around `:489`), replace:

```ts
      datasetCache.set(String(data.itemId), { collectionId: input.collectionId, columns: {} });
```

with:

```ts
      datasetCache.set(String(data.itemId), {
        collectionId: input.collectionId, columns: {}, timeField: null, reactsToExtent: false,
      });
```

Replace `getDatasetConfig`/`saveDatasetConfig` (`:497-505`):

```ts
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      return { source: "collection", collectionId: resolved.collectionId, columns: resolved.columns };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, { collectionId: config.collectionId, columns: config.columns });
    },
```

with:

```ts
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      return {
        source: "collection", collectionId: resolved.collectionId, columns: resolved.columns,
        timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
      };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, {
        collectionId: config.collectionId, columns: config.columns,
        timeField: config.timeField ?? null, reactsToExtent: config.reactsToExtent ?? false,
      });
    },
```

In `getAppConfig`/`getPublicAppConfig` (`:507-570`), both response-shape object types and both return statements need `interactions`. For each of the two methods, add `interactions?: "auto" | "manual";` right after the existing `navigationMode?: "tabs" | "story";` line inside the inline response type, and add `interactions: c.interactions,` right after `navigationMode: c.navigationMode,` in the returned object.

In `saveAppConfig` (around `:562-572`), add `interactions: config.interactions,` right after `navigationMode: config.navigationMode,`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file).

- [ ] **Step 6: Run the full shell unit suite and typecheck**

Run: `cd shell && npm run build`
Expected: PASS (`tsc --noEmit` catches any missed call site).

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): interactions/timeField/reactsToExtent dans les types et itemClient (SP-14b)"
```

---

### Task 5: Shell — fix the `bbox` bug in `buildAggregateBody`

**Files:**
- Modify: `shell/src/api/itemClient.ts:32-58` (`buildAggregateBody`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `buildAggregateBody(query)` now emits `body.bbox: [number, number, number, number]` (parsed from a `"minx,miny,maxx,maxy"` string on `query.bbox`) instead of leaking `bbox` into `body.filters`. This is the "correction incidente" from spec §3 — the first real consumer of `bbox` on the statistics path is Task 11 (map `reactsToExtent`), so this fix must land before that.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/api/itemClient.test.ts`, near the other `queryDataSource`/statistics tests:

```ts
test("queryDataSource sends a bbox query key as body.bbox, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "region", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", agg: "count", bbox: "1,2,3,4" },
  });
  expect(posted!.bbox).toEqual([1, 2, 3, 4]);
  expect(posted!.filters).toBeUndefined();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "bbox query key"`
Expected: FAIL — today `posted.filters` is `{ bbox: "1,2,3,4" }` and `posted.bbox` is `undefined`.

- [ ] **Step 3: Fix `buildAggregateBody`**

Replace (`shell/src/api/itemClient.ts:34-58`):

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures"]);

function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
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

with:

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox"]);

function parseBboxQueryValue(value: unknown): [number, number, number, number] | undefined {
  if (typeof value !== "string" || !value) return undefined;
  const parts = value.split(",").map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return undefined;
  return parts as [number, number, number, number];
}

function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file — confirm the pre-existing `featuresUrl strips reserved statistics keys` test, which doesn't touch `bbox`, is unaffected).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "fix(shell): bbox des sources statistics posé en body.bbox, plus absorbé dans filters (SP-14b)"
```

---

### Task 6: Shell — `DatasetEditPage` UI for `timeField`/`reactsToExtent`

**Files:**
- Modify: `shell/src/pages/DatasetEditPage.tsx`
- Test: `shell/src/pages/DatasetEditPage.test.tsx`

**Interfaces:**
- Consumes: `DatasetConfig.timeField`/`.reactsToExtent` (Task 4), `mergeDatasetSchema` (unchanged, `shell/src/lib/datasetSchema.ts`).
- Produces: two new controls saved together with the columns table by the existing "Enregistrer les colonnes" button (same `draft`/`save.mutate(draft)` flow — no new save button, per the SP-14a Task 8 lesson about colliding "Enregistrer" labels).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/pages/DatasetEditPage.test.tsx` (extend `datasetConfig`'s type usage; the existing `datasetConfig` const stays valid since the new fields are optional):

```ts
test("edits the time field and reacts-to-extent flag, and saves them with the columns", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
  });

  await screen.findByText("nom");
  await userEvent.selectOptions(screen.getByLabelText("Colonne temporelle"), "nom");
  await userEvent.click(screen.getByLabelText("Réagir au déplacement de la carte"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.timeField).toBe("nom");
  expect(savedConfig.reactsToExtent).toBe(true);
});

test("time field defaults to the empty option (no temporal context)", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn(),
  });
  await screen.findByText("nom");
  expect(screen.getByLabelText("Colonne temporelle")).toHaveValue("");
  expect(screen.getByLabelText("Réagir au déplacement de la carte")).not.toBeChecked();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx -t "time field|reacts-to-extent"`
Expected: FAIL — `getByLabelText("Colonne temporelle")` / `getByLabelText("Réagir au déplacement de la carte")` don't exist yet.

- [ ] **Step 3: Add the controls**

In `shell/src/pages/DatasetEditPage.tsx`, insert right after the `merged` computation and before the closing of the "Colonnes" `<div>` (i.e. right after the closing `</table>` block, still inside `<div>` at line ~92), replacing:

```tsx
        )}
      </div>
      <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
        Enregistrer les colonnes
      </Button>
```

with:

```tsx
        )}
        <label className="mt-2 flex flex-col gap-1 text-xs">
          Colonne temporelle
          <select
            aria-label="Colonne temporelle"
            className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
            value={draft.timeField ?? ""}
            onChange={(e) => setDraft((d) => (d ? { ...d, timeField: e.target.value || null } : d))}
          >
            <option value="">— aucune —</option>
            {merged.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label="Réagir au déplacement de la carte"
            checked={Boolean(draft.reactsToExtent)}
            onChange={(e) => setDraft((d) => (d ? { ...d, reactsToExtent: e.target.checked } : d))}
          />
          Réagir au déplacement de la carte
        </label>
      </div>
      <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
        Enregistrer les colonnes
      </Button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: PASS (all tests in the file, including the pre-existing one).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx
git commit -m "feat(shell): colonne temporelle et réagit-à-l'emprise dans l'édition de dataset (SP-14b)"
```

---

### Task 7: Shell — `analyticsContextUrl.ts` pure encode/decode

**Files:**
- Create: `shell/src/lib/analyticsContextUrl.ts`
- Test: `shell/src/lib/analyticsContextUrl.test.ts`
- (Type dependency created but not yet exported by Task 8 — see Step 3 note.)

**Interfaces:**
- Produces: `encodeAnalyticsContext(state: AnalyticsContextState): string`, `decodeAnalyticsContext(raw: string | null): AnalyticsContextState`. `AnalyticsContextState`/`EMPTY_ANALYTICS_CONTEXT` are defined in Task 8's `shell/src/builder/AnalyticsContext.tsx` — this task defines the type locally as a type-only forward declaration is awkward with a not-yet-existing module, so **this task creates `AnalyticsContextState`/`EMPTY_ANALYTICS_CONTEXT` directly in `AnalyticsContext.tsx` as a minimal type-and-constant-only file first**, and Task 8 extends that same file with the provider/hooks. This avoids any forward-reference or circular-task-ordering problem.

- [ ] **Step 1: Create the minimal `AnalyticsContext.tsx` (types + empty-state constant only)**

Create `shell/src/builder/AnalyticsContext.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
export const EXTENT_DEBOUNCE_MS = 500;

export type CrossFilterEntry = { field: string; value: string | string[]; originSourceId: string };

export type AnalyticsContextState = {
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, CrossFilterEntry | undefined>;
};

export const EMPTY_ANALYTICS_CONTEXT: AnalyticsContextState = { timeRange: null, extent: null, crossFilter: {} };
```

(Task 8 appends the provider/hooks to this same file — nothing here will need to change.)

- [ ] **Step 2: Write the failing tests**

Create `shell/src/lib/analyticsContextUrl.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { EMPTY_ANALYTICS_CONTEXT, type AnalyticsContextState } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "./analyticsContextUrl";

test("round-trips a full context through encode/decode", () => {
  const state: AnalyticsContextState = {
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: [1, 2, 3, 4],
    crossFilter: { "ds-1": { field: "région", value: "Île-de-France", originSourceId: "src-1" } },
  };
  expect(decodeAnalyticsContext(encodeAnalyticsContext(state))).toEqual(state);
});

test("decodes null/missing raw as the empty context", () => {
  expect(decodeAnalyticsContext(null)).toEqual(EMPTY_ANALYTICS_CONTEXT);
});

test("decodes garbage as the empty context, never throws", () => {
  expect(decodeAnalyticsContext("%%%not-base64%%%")).toEqual(EMPTY_ANALYTICS_CONTEXT);
});

test("encoded output is URL-safe (no +, /, or = padding)", () => {
  const state: AnalyticsContextState = {
    timeRange: null, extent: null,
    crossFilter: { "ds-1": { field: "f", value: ["a", "b", "c"], originSourceId: "s" } },
  };
  const encoded = encodeAnalyticsContext(state);
  expect(encoded).not.toMatch(/[+/=]/);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/analyticsContextUrl.test.ts`
Expected: FAIL — module `./analyticsContextUrl` doesn't exist.

- [ ] **Step 4: Implement**

Create `shell/src/lib/analyticsContextUrl.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { EMPTY_ANALYTICS_CONTEXT, type AnalyticsContextState } from "../builder/AnalyticsContext";

// Unicode-safe base64url: JSON can contain accented labels/values (field
// names, cross-filter values), so a plain btoa(json) would throw on any
// non-Latin1 character.
export function encodeAnalyticsContext(state: AnalyticsContextState): string {
  const json = JSON.stringify(state);
  const base64 = btoa(unescape(encodeURIComponent(json)));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeAnalyticsContext(raw: string | null): AnalyticsContextState {
  if (!raw) return EMPTY_ANALYTICS_CONTEXT;
  try {
    const base64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const json = decodeURIComponent(escape(atob(padded)));
    const parsed = JSON.parse(json) as Partial<AnalyticsContextState>;
    return {
      timeRange: parsed.timeRange ?? null,
      extent: parsed.extent ?? null,
      crossFilter: parsed.crossFilter ?? {},
    };
  } catch {
    return EMPTY_ANALYTICS_CONTEXT;
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsContextUrl.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/AnalyticsContext.tsx shell/src/lib/analyticsContextUrl.ts shell/src/lib/analyticsContextUrl.test.ts
git commit -m "feat(shell): type AnalyticsContextState + encodage URL base64url du contexte analytique (SP-14b)"
```

---

### Task 8: Shell — `AnalyticsContextProvider` (state, setters, no-op guard, extent debounce)

**Files:**
- Modify: `shell/src/builder/AnalyticsContext.tsx` (append provider + hooks to the file created in Task 7)
- Test: `shell/src/builder/AnalyticsContext.test.tsx`

**Interfaces:**
- Consumes: `AnalyticsContextState`, `EMPTY_ANALYTICS_CONTEXT`, `EXTENT_DEBOUNCE_MS`, `CrossFilterEntry` (Task 7, same file).
- Produces: `AnalyticsContextProvider({interactions, initialState, onStateChange, children})`, `useAnalyticsContext(): AnalyticsContextState`, `useSetTimeRange(): (range: {from:string;to:string}|null) => void`, `useSetExtent(): (bbox: [number,number,number,number]|null) => void`, `useSetCrossFilter(): (datasetId: string, field: string, value: string|string[], originSourceId: string) => void`. All setter hooks return **stable no-op-safe** functions usable with no provider mounted (default context values), matching the existing `useSetFilter()`/`useSetVariable()` pattern in this codebase.
- **Naming deviation from the design spec, intentional:** the design doc (§4-5) calls the 4th `setCrossFilter` argument `originWidgetId`. This plan uses `originSourceId` and — per Task 11/12/13 — widgets pass their own `props.dataSourceId` (the `DataSource.id`, not the widget's layout `item.id`). Reason: `DataContext.tsx` fetches data **per `DataSource`, shared by every widget bound to it** (see Task 10) — `derivePatch` only ever sees a `DataSource`, never the id of the specific widget instance rendering it, so "don't filter the widget that clicked" can only be implemented correctly by comparing against the `DataSource.id`. Two different widgets bound to the *same* `DataSource` sharing self-exclusion is an accepted, documented limitation (not a correctness bug: they already share one fetched result set).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/AnalyticsContext.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  AnalyticsContextProvider, useAnalyticsContext, useSetCrossFilter, useSetExtent, useSetTimeRange,
} from "./AnalyticsContext";

function Probe() {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  return (
    <div>
      <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>
      <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>
      <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>set-time</button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
    </div>
  );
}

test("setters are silent no-ops when interactions is not 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="manual"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

test("setTimeRange updates state when interactions is 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

test("hooks work with no provider mounted at all (default no-op context)", async () => {
  render(<Probe />);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

test("setCrossFilter toggles: same (field, value) twice clears it, a different value replaces it", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/"ds1":\{"field":"region","value":"Nord","originSourceId":"src1"\}/)).toBeInTheDocument();
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("setExtent debounces ~500ms before updating state", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await user.click(screen.getByText("set-extent"));
  expect(screen.getByText("extent:none")).toBeInTheDocument();
  vi.advanceTimersByTime(499);
  expect(screen.getByText("extent:none")).toBeInTheDocument();
  vi.advanceTimersByTime(1);
  expect(screen.getByText("extent:1,2,3,4")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: FAIL — `AnalyticsContextProvider`/`useAnalyticsContext`/etc. aren't exported yet.

- [ ] **Step 3: Implement**

Append to `shell/src/builder/AnalyticsContext.tsx` (after the `EMPTY_ANALYTICS_CONTEXT` constant from Task 7):

```tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type SetTimeRange = (range: { from: string; to: string } | null) => void;
type SetExtent = (bbox: [number, number, number, number] | null) => void;
type SetCrossFilter = (datasetId: string, field: string, value: string | string[], originSourceId: string) => void;

const AnalyticsStateContext = createContext<AnalyticsContextState>(EMPTY_ANALYTICS_CONTEXT);
const AnalyticsSettersContext = createContext<{ setTimeRange: SetTimeRange; setExtent: SetExtent; setCrossFilter: SetCrossFilter }>({
  setTimeRange: () => {}, setExtent: () => {}, setCrossFilter: () => {},
});

function sameCrossFilterValue(a: CrossFilterEntry["value"], b: CrossFilterEntry["value"]): boolean {
  return Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a) === JSON.stringify(b) : a === b;
}

export function AnalyticsContextProvider({
  interactions, initialState, onStateChange, children,
}: {
  interactions?: "auto" | "manual";
  initialState?: AnalyticsContextState;
  onStateChange?: (state: AnalyticsContextState) => void;
  children: ReactNode;
}) {
  const active = interactions === "auto";
  const [state, setState] = useState<AnalyticsContextState>(initialState ?? EMPTY_ANALYTICS_CONTEXT);
  const extentTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onStateChangeRef = useRef(onStateChange);
  useEffect(() => { onStateChangeRef.current = onStateChange; }, [onStateChange]);
  useEffect(() => { onStateChangeRef.current?.(state); }, [state]);
  useEffect(() => () => { if (extentTimer.current) clearTimeout(extentTimer.current); }, []);

  const setTimeRange = useCallback<SetTimeRange>((range) => {
    if (!active) return;
    setState((prev) => ({ ...prev, timeRange: range }));
  }, [active]);

  const setExtent = useCallback<SetExtent>((bbox) => {
    if (!active) return;
    if (extentTimer.current) clearTimeout(extentTimer.current);
    extentTimer.current = setTimeout(() => {
      setState((prev) => ({ ...prev, extent: bbox }));
    }, EXTENT_DEBOUNCE_MS);
  }, [active]);

  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const setters = useMemo(() => ({ setTimeRange, setExtent, setCrossFilter }), [setTimeRange, setExtent, setCrossFilter]);

  return (
    <AnalyticsSettersContext.Provider value={setters}>
      <AnalyticsStateContext.Provider value={state}>{children}</AnalyticsStateContext.Provider>
    </AnalyticsSettersContext.Provider>
  );
}

export function useAnalyticsContext(): AnalyticsContextState {
  return useContext(AnalyticsStateContext);
}
export function useSetTimeRange(): SetTimeRange {
  return useContext(AnalyticsSettersContext).setTimeRange;
}
export function useSetExtent(): SetExtent {
  return useContext(AnalyticsSettersContext).setExtent;
}
export function useSetCrossFilter(): SetCrossFilter {
  return useContext(AnalyticsSettersContext).setCrossFilter;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/AnalyticsContext.tsx shell/src/builder/AnalyticsContext.test.tsx
git commit -m "feat(shell): AnalyticsContextProvider — timeRange/extent/crossFilter, no-op hors mode auto (SP-14b)"
```

---

### Task 9: Shell — mount `AnalyticsContextProvider` in `AppRenderer`, add the interactions toggle in the builder

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx`

**Interfaces:**
- Consumes: `AnalyticsContextProvider`, `AnalyticsContextState` (Task 8).
- Produces: `AppRenderer` gains two new optional props, `initialAnalyticsContext?: AnalyticsContextState` and `onAnalyticsContextChange?: (state: AnalyticsContextState) => void` (both unused by every current caller except Task 17's `AppRuntimePage`, so this is fully additive). `ActionConditionBridge` moves inside `AnalyticsContextProvider` so `bus.setContext(...)` can include the live analytics context (needed by Task 12's CEL wiring).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/AppRenderer.test.tsx`:

```tsx
test("mounts AnalyticsContextProvider with config.interactions and a widget can read it", async () => {
  const cfg: AppConfig = {
    ...config,
    interactions: "auto",
    layout: { type: "grid", breakpoints: {}, items: [{ id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } }] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  // Smoke test: rendering with interactions:"auto" doesn't crash and still shows the widget.
  expect(screen.getByText("Salut")).toBeInTheDocument();
});
```

(This is a deliberately light smoke test — the real behavioral coverage of `AnalyticsContextProvider` lives in Task 8's `AnalyticsContext.test.tsx`, and of `DataContext`'s consumption in Task 10's tests. This test only proves the provider is mounted without breaking `AppRenderer`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "AnalyticsContextProvider"`
Expected: FAIL only if wiring is broken — actually since `interactions` is just an inert extra field on `config` today, this specific assertion would already pass before the change. Skip strict "must fail first" here and instead confirm it via the next test which is a true regression guard: add this second test which DOES fail today:

```tsx
test("a widget under AppRenderer can read the analytics context via useAnalyticsContext", async () => {
  const { getWidget, registerWidget: register } = await import("./registry");
  const { useAnalyticsContext } = await import("./AnalyticsContext");
  register({
    type: "__analytics_probe__", label: "probe", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: () => {
      const ctx = useAnalyticsContext();
      return <p>probe:{ctx.timeRange ? "set" : "empty"}</p>;
    },
  });
  const cfg: AppConfig = {
    ...config, interactions: "auto",
    layout: { type: "grid", breakpoints: {}, items: [{ id: "p1", widget: "__analytics_probe__", x: 0, y: 0, w: 4, h: 2, props: {} }] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(await screen.findByText("probe:empty")).toBeInTheDocument();
  expect(getWidget("__analytics_probe__")).toBeDefined();
});
```

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "can read the analytics context"`
Expected: FAIL — today there's no `AnalyticsContextProvider` in the tree, but this test would actually still pass because `useAnalyticsContext()` falls back to the default context value regardless. This confirms the test as written can't distinguish "provider mounted" from "provider absent" — replace the assertion with a stronger one that proves the provider (not just the hook's safe default) is present, by asserting `AnalyticsContextProvider`'s `interactions` guard is live:

```tsx
Component: () => {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  useEffect(() => { setTimeRange({ from: "a", to: "b" }); }, [setTimeRange]);
  return <p>probe:{ctx.timeRange ? "set" : "empty"}</p>;
},
```

(add `useEffect`, `useSetTimeRange` to the dynamic imports/usage). With `interactions: "auto"` on `cfg`, this now genuinely fails today (`probe:empty` forever, no provider to make `setTimeRange` do anything) and will pass once Task 9's wiring lands (`probe:set`).

Expected: FAIL.

- [ ] **Step 3: Wire the provider into `AppRenderer.tsx`**

In `shell/src/builder/AppRenderer.tsx`, add the import:

```ts
import { AnalyticsContextProvider, type AnalyticsContextState } from "./AnalyticsContext";
```

Extend the props destructuring and type:

```ts
export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
  breakpoint,
  pageId,
  onNavigate,
  initialAnalyticsContext,
  onAnalyticsContextChange,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  breakpoint?: Breakpoint;
  pageId?: string;
  onNavigate?: (pageId: string) => void;
  initialAnalyticsContext?: AnalyticsContextState;
  onAnalyticsContextChange?: (state: AnalyticsContextState) => void;
}) {
```

Replace the render tree's provider nesting:

```tsx
        <ActionBusProvider bus={bus}>
          <VariablesProvider variables={config.variables ?? []}>
            <ActionConditionBridge bus={bus} />
            {(config.variables ?? []).map((v) => (
              <VariableBusBridge key={v.id} variable={v} bus={bus} />
            ))}
            <DataProvider sources={config.dataSources}>
              <GridCanvas
                items={activeLayout.items}
                breakpoint={bp}
                editable={editable}
                selectedId={selectedId}
                onSelect={(id) => onSelect?.(id)}
                onMoveItem={handleMove}
                renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} />}
              />
            </DataProvider>
          </VariablesProvider>
        </ActionBusProvider>
```

with:

```tsx
        <ActionBusProvider bus={bus}>
          <VariablesProvider variables={config.variables ?? []}>
            <AnalyticsContextProvider
              interactions={config.interactions}
              initialState={initialAnalyticsContext}
              onStateChange={onAnalyticsContextChange}
            >
              <ActionConditionBridge bus={bus} />
              {(config.variables ?? []).map((v) => (
                <VariableBusBridge key={v.id} variable={v} bus={bus} />
              ))}
              <DataProvider sources={config.dataSources}>
                <GridCanvas
                  items={activeLayout.items}
                  breakpoint={bp}
                  editable={editable}
                  selectedId={selectedId}
                  onSelect={(id) => onSelect?.(id)}
                  onMoveItem={handleMove}
                  renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} />}
                />
              </DataProvider>
            </AnalyticsContextProvider>
          </VariablesProvider>
        </ActionBusProvider>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Add the "Interactions automatiques" toggle to `AppBuilderPage.tsx`**

In `shell/src/pages/AppBuilderPage.tsx`, add a setter next to `setNavigationMode` (`:155-156`):

```ts
  const setNavigationMode = (navigationMode: "tabs" | "story") =>
    setDraft((d) => (d ? { ...d, navigationMode } : d));
```

becomes:

```ts
  const setNavigationMode = (navigationMode: "tabs" | "story") =>
    setDraft((d) => (d ? { ...d, navigationMode } : d));

  const setInteractions = (interactions: "auto" | "manual") =>
    setDraft((d) => (d ? { ...d, interactions } : d));
```

Then, right after the `<NavigationPanel .../>` block in the JSX (`:213-218`), add:

```tsx
              <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Interactions</p>
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  aria-label="Interactions automatiques (cross-filter)"
                  checked={draft.interactions === "auto"}
                  onChange={(e) => setInteractions(e.target.checked ? "auto" : "manual")}
                />
                Interactions automatiques (cross-filter)
              </label>
```

- [ ] **Step 6: Add a builder-level test for the toggle**

Add to `shell/src/pages/AppBuilderPage.test.tsx` (uses the file's existing `renderPage`/`config` helpers, same pattern as its `"adds a widget from the palette and saves the config"` test):

```tsx
test("toggles interactions on and saves it with the app config", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByLabelText("Interactions automatiques (cross-filter)");
  expect(screen.getByLabelText("Interactions automatiques (cross-filter)")).not.toBeChecked();
  await userEvent.click(screen.getByLabelText("Interactions automatiques (cross-filter)"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.interactions).toBe("auto");
});
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx src/builder/AppRenderer.test.tsx`
Expected: PASS.

- [ ] **Step 8: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): monte AnalyticsContextProvider dans AppRenderer, toggle interactions dans le builder (SP-14b)"
```

---

### Task 10: Shell — `derivePatch` pure function

**Files:**
- Create: `shell/src/lib/analyticsPatch.ts`
- Test: `shell/src/lib/analyticsPatch.test.ts`

**Interfaces:**
- Consumes: `DataSource`, `DatasetConfig` (`shell/src/api/types.ts`), `AnalyticsContextState` (`shell/src/builder/AnalyticsContext.tsx`).
- Produces: `derivePatch(source: DataSource, ctx: AnalyticsContextState, datasets: Record<string, DatasetConfig>): Record<string, unknown>` — used by Task 11's `DataContext.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/lib/analyticsPatch.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { derivePatch } from "./analyticsPatch";

const EMPTY: AnalyticsContextState = { timeRange: null, extent: null, crossFilter: {} };

const source: DataSource = { id: "src-1", type: "features", service: "core", layer: "parcs", datasetId: "ds-1", query: {} };
const dataset: DatasetConfig = { source: "collection", collectionId: "parcs", columns: {}, timeField: "date_releve", reactsToExtent: true };

test("returns {} when the source has no datasetId", () => {
  const inline: DataSource = { id: "src-2", type: "features", service: "core", layer: "parcs", query: {} };
  expect(derivePatch(inline, { ...EMPTY, timeRange: { from: "a", to: "b" } }, {})).toEqual({});
});

test("returns {} when the dataset isn't resolved yet", () => {
  expect(derivePatch(source, { ...EMPTY, timeRange: { from: "a", to: "b" } }, {})).toEqual({});
});

test("adds field__gte/field__lte when timeRange is set and the dataset has a timeField", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, timeRange: { from: "2026-01-01", to: "2026-02-01" } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({
    date_releve__gte: "2026-01-01", date_releve__lte: "2026-02-01",
  });
});

test("skips the time patch when the dataset has no timeField", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, timeRange: { from: "a", to: "b" } };
  const noTimeField = { ...dataset, timeField: null };
  expect(derivePatch(source, ctx, { "ds-1": noTimeField })).toEqual({});
});

test("adds bbox when extent is set and the dataset reactsToExtent", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, extent: [1, 2, 3, 4] };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ bbox: "1,2,3,4" });
});

test("skips the extent patch when reactsToExtent is false", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, extent: [1, 2, 3, 4] };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false } })).toEqual({});
});

test("adds a cross-filter patch for a different origin source", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-OTHER" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ region: "Nord" });
});

test("excludes the cross-filter patch when this source is the origin", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-1" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});

test("uses field__in with a comma-joined value for an array cross-filter value", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: ["Nord", "Sud"], originSourceId: "src-OTHER" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ region__in: "Nord,Sud" });
});

test("combines time, extent and cross-filter patches together", () => {
  const ctx: AnalyticsContextState = {
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: [1, 2, 3, 4],
    crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({
    date_releve__gte: "2026-01-01", date_releve__lte: "2026-02-01",
    bbox: "1,2,3,4", region: "Nord",
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Create `shell/src/lib/analyticsPatch.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";

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

  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    else patch[crossFilter.field] = crossFilter.value;
  }

  return patch;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/lib/analyticsPatch.ts shell/src/lib/analyticsPatch.test.ts
git commit -m "feat(shell): derivePatch — traduit le contexte analytique en filtres de requête (SP-14b)"
```

---

### Task 11: Shell — `DataContext.tsx` wires dataset/schema resolution and `derivePatch`

**Files:**
- Modify: `shell/src/builder/DataContext.tsx`
- Test: `shell/src/builder/DataContext.test.tsx`

**Interfaces:**
- Consumes: `derivePatch` (Task 10), `useAnalyticsContext` (Task 8), `client.getDatasetConfig`/`client.getCollectionSchema` (existing `ItemClient` methods, Task 4 extended the former).
- Produces: `DataSourceState` gains `datasetId?: string` and `pkColumn?: string` (both read directly off `ctx.data` by widgets in Tasks 12-14 — no hooks needed at the widget level, so widget unit tests never need a `QueryClientProvider` for cross-filter). `DataProvider`'s existing public API (`sources`/`children` props, `useDataStates()`, `useSetFilter()`) is unchanged.

- [ ] **Step 1: Extend `DataSourceState`**

In `shell/src/api/types.ts`, replace:

```ts
export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
};
```

with:

```ts
export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
  datasetId?: string;
  pkColumn?: string;
};
```

- [ ] **Step 2: Write the failing tests**

Add to `shell/src/builder/DataContext.test.tsx` (needs `AnalyticsContextProvider` import and a dataset-bound source):

```tsx
import { AnalyticsContextProvider } from "./AnalyticsContext";

test("resolves datasetId and pkColumn onto the DataSourceState for a dataset-bound source", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: {} }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs", columns: {}, timeField: null, reactsToExtent: false }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", datasetId: "dataset-1", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    return <p>datasetId:{s?.datasetId ?? "none"} pkColumn:{s?.pkColumn ?? "none"}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="manual">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText(/datasetId:dataset-1/)).toBeInTheDocument());
  expect(screen.getByText(/pkColumn:id/)).toBeInTheDocument();
});

test("applies the analytics context's time patch to a dataset-bound source's query", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([]);
  const client = {
    queryDataSource,
    featuresUrl: vi.fn().mockReturnValue(""),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs", columns: {}, timeField: "date_releve", reactsToExtent: false }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", datasetId: "dataset-1", query: {} }];

  function Probe() {
    useDataStates();
    return <p>rendered</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await screen.findByText("rendered");
  // The provider starts with an empty context (no timeRange set), so the
  // first fetch has no time patch — this test only proves getDatasetConfig
  // is actually consulted and doesn't crash the query pipeline.
  await waitFor(() => expect(client.getDatasetConfig).toHaveBeenCalledWith("dataset-1"));
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx -t "datasetId and pkColumn|applies the analytics context"`
Expected: FAIL — `getDatasetConfig`/`getCollectionSchema` are never called, `datasetId`/`pkColumn` are `undefined` on the state.

- [ ] **Step 4: Implement**

Replace `shell/src/builder/DataContext.tsx` in full:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { DataSource, DataSourceState, DatasetConfig } from "../api/types";
import { useAnalyticsContext } from "./AnalyticsContext";
import { derivePatch } from "../lib/analyticsPatch";

type SetFilter = (sourceId: string, query: Record<string, unknown>) => void;

const DataStatesContext = createContext<Record<string, DataSourceState>>({});
const SetFilterContext = createContext<SetFilter>(() => {});

export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
  const analyticsCtx = useAnalyticsContext();
  const [filters, setFilters] = useState<Record<string, Record<string, unknown>>>({});
  const setFilter = useCallback<SetFilter>((sourceId, query) => {
    setFilters((prev) => ({ ...prev, [sourceId]: query }));
  }, []);

  // Resolve DatasetConfig for every distinct datasetId referenced by `sources`
  // — same queryKey ("dataset", pk) as useDatasetConfig() elsewhere, so React
  // Query dedups the fetch, and getDatasetConfig() itself dedups further via
  // itemClient's internal resolveDataset cache.
  const datasetIds = [...new Set(sources.map((s) => s.datasetId).filter((id): id is string => Boolean(id)))];
  const datasetResults = useQueries({
    queries: datasetIds.map((id) => ({ queryKey: ["dataset", id], queryFn: () => client.getDatasetConfig(id) })),
  });
  const datasets: Record<string, DatasetConfig> = {};
  datasetIds.forEach((id, i) => {
    const data = datasetResults[i].data;
    if (data) datasets[id] = data;
  });

  // Resolve the primary-key column name for every distinct collection behind
  // those datasets, so table/map widgets can cross-filter by pk without
  // fetching a schema themselves (they only read ctx.data.pkColumn).
  const collectionIds = [...new Set(Object.values(datasets).map((d) => d.collectionId))];
  const schemaResults = useQueries({
    queries: collectionIds.map((id) => ({ queryKey: ["collection-schema", id], queryFn: () => client.getCollectionSchema(id) })),
  });
  const pkByCollection: Record<string, string> = {};
  collectionIds.forEach((id, i) => {
    const data = schemaResults[i].data;
    if (data) pkByCollection[id] = data.pk;
  });

  function mergedQueryFor(s: DataSource): DataSource {
    const contextPatch = derivePatch(s, analyticsCtx, datasets);
    return { ...s, query: { ...s.query, ...contextPatch, ...(filters[s.id] ?? {}) } };
  }

  const results = useQueries({
    queries: sources.map((s) => {
      const merged = mergedQueryFor(s);
      return {
        queryKey: ["datasource", s.id, merged.query],
        queryFn: () => client.queryDataSource(merged),
      };
    }),
  });

  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    const merged = mergedQueryFor(s);
    const dataset = s.datasetId ? datasets[s.datasetId] : undefined;
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      layer: s.layer,
      url: s.type === "features" ? client.featuresUrl(merged) : undefined,
      datasetId: s.datasetId,
      pkColumn: dataset ? pkByCollection[dataset.collectionId] : undefined,
    };
  });

  return (
    <SetFilterContext.Provider value={setFilter}>
      <DataStatesContext.Provider value={states}>{children}</DataStatesContext.Provider>
    </SetFilterContext.Provider>
  );
}

export function useDataStates(): Record<string, DataSourceState> {
  return useContext(DataStatesContext);
}

export function useSetFilter(): SetFilter {
  return useContext(SetFilterContext);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: PASS (including the two pre-existing tests, which use sources without `datasetId` — `datasetIds`/`collectionIds` end up empty, `useQueries({queries: []})` fires no request, `getDatasetConfig`/`getCollectionSchema` are never called, so the existing mock `client` objects that don't implement those methods still work).

- [ ] **Step 6: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/DataContext.tsx shell/src/builder/DataContext.test.tsx
git commit -m "feat(shell): DataContext résout dataset/pkColumn et applique derivePatch (SP-14b)"
```

---

### Task 12: Shell — CEL `ctx.*` binding in `WidgetHost`/`ActionConditionBridge`

**Files:**
- Modify: `shell/src/builder/expr.ts`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx` (`ActionConditionBridge`)
- Test: `shell/src/builder/expr.test.ts`, `shell/src/builder/WidgetHost.test.tsx`, `shell/src/builder/configExpressionErrors.test.ts`

**Interfaces:**
- Produces: `ExprContext.ctx?: AnalyticsContextState` — an additive optional key, distinct from `vars` (no collision with an app variable of the same name). `evaluateExpression`/`resolveExprBindings`/`validateExpression` need no signature change (they already take/produce a generic `ExprContext`/pass through). `WidgetHost.tsx`'s `exprCtx` and `ActionBus.setContext(...)` calls both gain `ctx: analyticsCtx`.
- **Design note, not a code change:** the spec (§5) suggests `configExpressionErrors.ts` needs new logic to "recognize" the `ctx.*` prefix. Investigation shows `validateExpression` calls cel-js's `parse(expression)`, which is **syntax-only** — it has no notion of declared identifiers/prefixes (confirmed via `cel-js`'s `.d.ts`: `parse(expression: string): ParseResult` takes no context). So `ctx.timeRange.from` already parses successfully with zero code change. This task adds a regression test that locks in that already-correct behavior instead of adding dead code.

- [ ] **Step 1: Write the failing test for `ExprContext`**

Add to `shell/src/builder/expr.test.ts`:

```ts
test("evaluateExpression can read the ctx.* analytics binding", () => {
  const result = evaluateExpression("ctx.timeRange.from", {
    vars: {}, user: { name: "" },
    ctx: { timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {} },
  });
  expect(result).toBe("2026-01-01");
});

test("evaluateExpression tolerates a missing ctx binding (no provider mounted)", () => {
  const result = evaluateExpression("vars.x", { vars: { x: 1 }, user: { name: "" } });
  expect(result).toBe(1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/expr.test.ts -t "ctx"`
Expected: FAIL — TypeScript compile error (`ctx` doesn't exist on `ExprContext`) surfaces as a vitest/tsc failure.

- [ ] **Step 3: Extend `ExprContext`**

In `shell/src/builder/expr.ts`, replace:

```ts
export type ExprContext = {
  vars: Record<string, unknown>;
  record?: Record<string, unknown>;
  user: { name: string };
};
```

with:

```ts
import type { AnalyticsContextState } from "./AnalyticsContext";

export type ExprContext = {
  vars: Record<string, unknown>;
  record?: Record<string, unknown>;
  user: { name: string };
  ctx?: AnalyticsContextState;
};
```

(add the `import type` at the top of the file, before the existing `import { evaluate, parse } from "cel-js";`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/expr.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire `WidgetHost.tsx`**

In `shell/src/builder/WidgetHost.tsx`, add the import:

```ts
import { useAnalyticsContext } from "./AnalyticsContext";
```

Replace:

```tsx
  const states = useDataStates();
  const bus = useActionBus();
  const variables = useVariables();
  const { username } = useAuth();
  const user = { name: username ?? "" };
```

with:

```tsx
  const states = useDataStates();
  const bus = useActionBus();
  const variables = useVariables();
  const { username } = useAuth();
  const analyticsCtx = useAnalyticsContext();
  const user = { name: username ?? "" };
```

Replace both occurrences of `{ vars: variables, record: data?.records[0]?.properties, user }` (the `visible` check and `exprCtx`) with `{ vars: variables, record: data?.records[0]?.properties, user, ctx: analyticsCtx }`.

- [ ] **Step 6: Wire `ActionConditionBridge` in `AppRenderer.tsx`**

Replace:

```tsx
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useAuth();
  useEffect(() => {
    bus.setContext({ vars: variables, user: { name: username ?? "" } });
  }, [bus, variables, username]);
  return null;
}
```

with:

```tsx
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useAuth();
  const analyticsCtx = useAnalyticsContext();
  useEffect(() => {
    bus.setContext({ vars: variables, user: { name: username ?? "" }, ctx: analyticsCtx });
  }, [bus, variables, username, analyticsCtx]);
  return null;
}
```

(add `useAnalyticsContext` to the existing `import { AnalyticsContextProvider, type AnalyticsContextState } from "./AnalyticsContext";` from Task 9 — becomes `import { AnalyticsContextProvider, useAnalyticsContext, type AnalyticsContextState } from "./AnalyticsContext";`). Note `ActionConditionBridge` is already nested inside `AnalyticsContextProvider` since Task 9 — no JSX reordering needed here.

- [ ] **Step 7: Add the `configExpressionErrors` regression test**

Add to `shell/src/builder/configExpressionErrors.test.ts` (match the file's existing `AppConfig` fixture-building pattern):

```ts
test("accepts a visibleWhen expression referencing the ctx.* analytics prefix (cel-js parse is syntax-only)", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "ctx.timeRange != null" },
    ] },
  };
  expect(getConfigExpressionErrors(config)).toEqual([]);
});
```

- [ ] **Step 8: Run all the affected tests**

Run: `cd shell && npx vitest run src/builder/expr.test.ts src/builder/WidgetHost.test.tsx src/builder/AppRenderer.test.tsx src/builder/configExpressionErrors.test.ts`
Expected: PASS.

- [ ] **Step 9: Run the full shell unit suite and typecheck**

Run: `cd shell && npm run build`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/expr.ts shell/src/builder/expr.test.ts shell/src/builder/WidgetHost.tsx shell/src/builder/AppRenderer.tsx shell/src/builder/configExpressionErrors.test.ts
git commit -m "feat(shell): expose le contexte analytique aux expressions CEL (ctx.*) (SP-14b)"
```

---

### Task 13: Shell — Chart cross-filter (`EChart.tsx` + `chart.tsx`)

**Files:**
- Modify: `shell/src/builder/EChart.tsx`
- Modify: `shell/src/builder/widgets/chart.tsx`
- Test: `shell/src/builder/widgets/chart.test.tsx`

**Interfaces:**
- Consumes: `useSetCrossFilter` (Task 8), `ctx.data.datasetId` (Task 11).
- Produces: `EChart` gains an optional `onClick?: (params: { name?: string }) => void` prop, forwarded to the real ECharts instance's `click` event. `chart` widget gains `events: ["categorySelected"]`; on click it always emits `{[categoryField]: value}` on the bus (manual-wiring channel, unconditional) and, when a `datasetId` is available, calls `setCrossFilter(datasetId, categoryField, value, dataSourceId)` (a silent no-op unless `interactions === "auto"`, per Task 8 — no extra `if` needed for that guard).

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/builder/widgets/chart.test.tsx`. First extend the `vi.mock("../EChart", ...)` at the top of the file to forward `onClick` so tests can simulate a click:

```tsx
vi.mock("../EChart", () => ({
  EChart: ({ option, onClick }: { option: { series?: unknown }; onClick?: (params: { name?: string }) => void }) => {
    const s = option.series;
    const n = Array.isArray(s) ? s.length : s ? 1 : 0;
    return (
      <div data-testid="echart" data-series={n} onClick={() => onClick?.({ name: "Nord" })} />
    );
  },
}));
```

Then add:

```tsx
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";

test("declares the categorySelected event", () => {
  expect(getWidget("chart")!.events).toEqual(["categorySelected"]);
});

test("clicking a category always emits categorySelected on the bus", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "chart1", event: "categorySelected", to: "sink", action: "log" }]);
  const Chart = getWidget("chart")!.Component;
  render(<Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide, bus, widgetId: "chart1" } as WidgetContext} />);
  await userEvent.click(await screen.findByTestId("echart"));
  expect(handler).toHaveBeenCalledWith({ region: "Nord" });
});

test("sets the cross-filter when interactions is auto and the source is dataset-bound", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Chart = getWidget("chart")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Chart props={{ categoryField: "region", chartType: "bar", dataSourceId: "src-1" }}
        ctx={{ mode: "runtime", data: { ...wide, datasetId: "dataset-1" } } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("does not set a cross-filter when the source has no datasetId (manual wiring only)", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const Chart = getWidget("chart")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx -t "categorySelected|cross-filter"`
Expected: FAIL — `events` is `undefined`, clicking the mock `echart` div does nothing (no `onClick` prop wired).

- [ ] **Step 3: Add `onClick` to `EChart.tsx`**

Replace `shell/src/builder/EChart.tsx`'s function signature and mount effect:

```tsx
export function EChart({ option, className }: { option: EChartsOption; className?: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);
```

with:

```tsx
export function EChart({ option, className, onClick }: {
  option: EChartsOption; className?: string; onClick?: (params: { name?: string; value?: unknown }) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onClickRef = useRef(onClick);
  useEffect(() => { onClickRef.current = onClick; }, [onClick]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    chart.on("click", (params) => onClickRef.current?.(params as { name?: string; value?: unknown }));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);
```

- [ ] **Step 4: Wire `chart.tsx`**

In `shell/src/builder/widgets/chart.tsx`, add the import:

```ts
import { useSetCrossFilter } from "../AnalyticsContext";
```

Add `events: ["categorySelected"],` right after `defaultSize: { w: 6, h: 4 },`.

Replace the `Component`:

```tsx
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      return (
        <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
          <EChart option={option} />
        </Suspense>
      );
    },
```

with:

```tsx
    Component: ({ props, ctx }) => {
      const setCrossFilter = useSetCrossFilter();
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      const categoryField = String(props.categoryField ?? "");
      function handleClick(params: { name?: string }) {
        if (!categoryField) return;
        const value = params.name != null ? String(params.name) : "";
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [categoryField]: value });
        if (data?.datasetId) setCrossFilter(data.datasetId, categoryField, value, String(props.dataSourceId ?? ""));
      }
      return (
        <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
          <EChart option={option} onClick={handleClick} />
        </Suspense>
      );
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 6: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/EChart.tsx shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx
git commit -m "feat(shell): cross-filter automatique au clic sur une catégorie du graphique (SP-14b)"
```

---

### Task 14: Shell — Table/List cross-filter (`data.tsx`)

**Files:**
- Modify: `shell/src/builder/widgets/data.tsx`
- Test: `shell/src/builder/widgets/data.test.tsx`

**Interfaces:**
- Consumes: `useSetCrossFilter` (Task 8), `ctx.data.datasetId`/`ctx.data.pkColumn` (Task 11).
- Produces: both the `list` and `table` widgets' row-click handler additionally calls `setCrossFilter(datasetId, pkColumn, String(r.id), dataSourceId)` when both `datasetId` and `pkColumn` are present — the existing `ctx.bus?.emit(..., "itemSelected", r)` is untouched.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/builder/widgets/data.test.tsx` (read the file first to match its existing `ctx`/`state`/fixture helpers before finalizing variable names):

```tsx
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";

function CrossFilterProbe({ datasetId }: { datasetId: string }) {
  const ctx = useAnalyticsContext();
  const entry = ctx.crossFilter[datasetId];
  return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
}

test("table row click sets the cross-filter by pkColumn when dataset-bound and interactions is auto", async () => {
  const Table = getWidget("table")!.Component;
  const data = { loading: false, error: false, records: [{ id: 1, properties: { nom: "Parc A" } }], datasetId: "dataset-1", pkColumn: "id" };
  render(
    <AnalyticsContextProvider interactions="auto">
      <Table props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A").closest("tr")!);
  expect(await screen.findByText("cf:id=1")).toBeInTheDocument();
});

test("list item click does not set a cross-filter when the source isn't dataset-bound", async () => {
  const List = getWidget("list")!.Component;
  const data = { loading: false, error: false, records: [{ id: 1, properties: { nom: "Parc A" } }] };
  render(
    <AnalyticsContextProvider interactions="auto">
      <List props={{ dataSourceId: "src-1", titleField: "nom" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A"));
  expect(await screen.findByText("cf:none")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx -t "cross-filter"`
Expected: FAIL — clicking a row never touches the analytics context.

- [ ] **Step 3: Implement**

In `shell/src/builder/widgets/data.tsx`, add the import:

```ts
import { useSetCrossFilter } from "../AnalyticsContext";
```

In the `list` widget's `Component`, after `const setFilter = useSetFilter();`, add:

```tsx
      const setCrossFilter = useSetCrossFilter();
```

and replace the `<li ... onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r)}>` handler body with a named function used by both the list and table widgets (define once, reuse):

```tsx
      function selectRecord(r: DataRecord) {
        ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r);
        const datasetId = ctx.data?.datasetId;
        const pkColumn = ctx.data?.pkColumn;
        if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(r.id), String(props.dataSourceId ?? ""));
      }
```

placed right before the `return (` of the `list` Component, and change the `<li>`'s `onClick` to `onClick={() => selectRecord(r)}`.

Apply the same three changes to the `table` widget's `Component`: add `const setCrossFilter = useSetCrossFilter();` after its own `const setFilter = useSetFilter();`, add the same `selectRecord` function before its `return (`, and change the `<tr>`'s `onClick` from `() => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r)` to `() => selectRecord(r)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: PASS (all tests in the file, including the pre-existing `itemSelected`/`setFilter` ones — `ctx.data` in those tests has no `datasetId`, so `selectRecord` still emits `itemSelected` but skips the cross-filter branch).

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/data.tsx shell/src/builder/widgets/data.test.tsx
git commit -m "feat(shell): cross-filter automatique au clic sur une ligne de liste/table (SP-14b)"
```

---

### Task 15: Shell — Map extent + cross-filter (`MapView.tsx` + `mapWidget.tsx`)

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/test/MockMaplibreMap.ts` (test double, gains `getBounds()`)
- Test: `shell/src/map/MapView.test.tsx`, `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Produces: `MapView`'s `onViewChange` callback gains a `bbox: [number, number, number, number]` field (alongside the existing `center`/`zoom`) computed from `map.getBounds().toArray()` on `moveend`. `mapWidget`'s `Component` calls `useSetExtent(bbox)` on every `onViewChange` (no widget-level debounce — Task 8's provider already debounces `setExtent` internally) and, on feature click, additionally calls `setCrossFilter(datasetId, pkColumn, featureId, dataSourceId)` when both are present (mirrors Task 14's table logic).

- [ ] **Step 1: Add `getBounds()` to the `MockMaplibreMap` test double**

`shell/src/map/MapView.test.tsx` drives the map through `mapInstances[0]` (a `MockMap` from `shell/src/test/MockMaplibreMap.ts`) and fires `"moveend"` via `mapInstances[0].fire("moveend")` (see its existing `"reports view changes on moveend"` test). `MockMap` has no `getBounds()` yet — add one. In `shell/src/test/MockMaplibreMap.ts`, add a `bounds` field (test-settable, default matches nothing in particular since every test that cares sets it explicitly) and a `getBounds()` method:

```ts
  bounds: [[number, number], [number, number]] = [[0, 0], [0, 0]];
```

(add this field declaration next to `flyToArgs: unknown[] = [];`), and:

```ts
  getBounds() {
    return { toArray: () => this.bounds };
  }
```

(add this method next to `getZoom()`).

- [ ] **Step 2: Write the failing test for `MapView.tsx`**

Add to `shell/src/map/MapView.test.tsx`, right after the existing `"reports view changes on moveend"` test:

```ts
test("onViewChange includes the current bbox from the map bounds", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].bounds = [[1, 2], [3, 4]];
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5, bbox: [1, 2, 3, 4] });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "bbox"`
Expected: FAIL — `onViewChange` today only forwards `{center, zoom}`, so the callback is never called with a `bbox` key (Step 1's `getBounds()` addition is exercised but its result is discarded).

- [ ] **Step 4: Implement the bbox in `MapView.tsx`**

In `shell/src/map/MapView.tsx`, update the `onViewChange` prop type on the `forwardRef` generic:

```ts
export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
    onFeatureClick?: (record: DataRecord) => void;
  }
>(function MapView({ config, onViewChange, onFeatureClick }, ref) {
```

becomes:

```ts
export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void;
    onFeatureClick?: (record: DataRecord) => void;
  }
>(function MapView({ config, onViewChange, onFeatureClick }, ref) {
```

Replace the `moveend` handler:

```ts
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      cb({ center: [c.lng, c.lat], zoom: map.getZoom() });
    });
```

with:

```ts
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      cb({ center: [c.lng, c.lat], zoom: map.getZoom(), bbox: bounds });
    });
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS.

- [ ] **Step 6: Write the failing tests for `mapWidget.tsx`**

Add to `shell/src/builder/widgets/mapWidget.test.tsx`. First extend the `vi.mock("../../map/MapView", ...)` mock's `onViewChange` call at the top of the file to include `bbox`:

```tsx
<div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}>
```

(update the mock's inline type for `onViewChange` accordingly: `(v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void`).

Then add:

```tsx
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  vi.useFakeTimers();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
      <ExtentProbe />
    </AnalyticsContextProvider>,
  );
  await user.click(await screen.findByTestId("mapview"));
  vi.advanceTimersByTime(500);
  expect(await screen.findByText("extent:10,20,30,40")).toBeInTheDocument();
  vi.useRealTimers();
});

test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText("cf:id=1")).toBeInTheDocument();
});
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "extent|cross-filter"`
Expected: FAIL — moving the map / clicking a feature never touches the analytics context.

- [ ] **Step 8: Implement in `mapWidget.tsx`**

Add the import:

```ts
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
```

In the `map` widget's `Component`, after `const handle = useRef<MapViewHandle>(null);`, add:

```tsx
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
```

Replace the `<MapView ... />` return:

```tsx
          <MapView
            ref={handle}
            config={config}
            onViewChange={(v) => ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v)}
            onFeatureClick={(record) => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record)}
          />
```

with:

```tsx
          <MapView
            ref={handle}
            config={config}
            onViewChange={(v) => {
              ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
              setExtent(v.bbox);
            }}
            onFeatureClick={(record) => {
              ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
              const datasetId = ctx.data?.datasetId;
              const pkColumn = ctx.data?.pkColumn;
              if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""));
            }}
          />
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS (all tests in the file, including the pre-existing `extentChanged` bus test, which doesn't wrap `AnalyticsContextProvider` — `useSetExtent()`'s default no-op context value keeps it passing unchanged).

- [ ] **Step 10: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/test/MockMaplibreMap.ts shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): la carte pilote l'emprise globale et le cross-filter au clic sur une entité (SP-14b)"
```

---

### Task 16: Shell — new `dateRangeFilter` widget

**Files:**
- Create: `shell/src/builder/widgets/dateRangeFilter.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/widgets/dateRangeFilter.test.tsx`

**Interfaces:**
- Consumes: `useSetTimeRange` (Task 8).
- Produces: `registerDateRangeFilterWidget()`, a `dateRangeFilter` widget type with `defaultProps: { label: "Période" }`, `defaultSize: { w: 4, h: 1 }`, **no** `events`/`actions` (it's a global control, unlike `filter.tsx` which targets one `DataSource` via the bus).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/dateRangeFilter.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { registerDateRangeFilterWidget } from "./dateRangeFilter";
import type { WidgetContext } from "../registry";

beforeEach(() => { _resetRegistry(); registerDateRangeFilterWidget(); });

function TimeRangeProbe() {
  const ctx = useAnalyticsContext();
  return <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
}

test("registers with no events/actions (a global control, not a bus-wired source filter)", () => {
  const def = getWidget("dateRangeFilter")!;
  expect(def.events).toBeUndefined();
  expect(def.actions).toBeUndefined();
});

test("sets the time range when both dates are filled, only when interactions is auto", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilter props={{ label: "Période" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(await screen.findByText("timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

test("is a no-op when interactions is manual", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="manual">
      <DateRangeFilter props={{ label: "Période" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Create `shell/src/builder/widgets/dateRangeFilter.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import { useSetTimeRange } from "../AnalyticsContext";

export function registerDateRangeFilterWidget(): void {
  registerWidget({
    type: "dateRangeFilter",
    label: "Plage de dates",
    defaultProps: { label: "Période" },
    defaultSize: { w: 4, h: 1 },
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">Libellé
        <input aria-label="Libellé de la plage de dates" className="h-9 rounded-md border border-slate-300 px-2"
          value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
      </label>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [from, setFrom] = useState("");
      const [to, setTo] = useState("");

      function update(nextFrom: string, nextTo: string) {
        setFrom(nextFrom);
        setTo(nextTo);
        setTimeRange(nextFrom && nextTo ? { from: nextFrom, to: nextTo } : null);
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? "Période")}</span>
          <div className="flex gap-2">
            <input type="date" aria-label="Date de début" className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={from} onChange={(e) => update(e.target.value, to)} />
            <input type="date" aria-label="Date de fin" className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={to} onChange={(e) => update(from, e.target.value)} />
          </div>
        </div>
      );
    },
  });
}
```

Register it in `shell/src/builder/widgets/index.tsx`: add the import `import { registerDateRangeFilterWidget } from "./dateRangeFilter";` and add `registerDateRangeFilterWidget();` to the end of `registerBuiltinWidgets()`, right after `registerDatasetCardWidget();`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/dateRangeFilter.tsx shell/src/builder/widgets/dateRangeFilter.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): widget Plage de dates, pilote timeRange globalement (SP-14b)"
```

---

### Task 17: Shell — URL sync in `AppRuntimePage.tsx`

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppRuntimePage.test.tsx`

**Interfaces:**
- Consumes: `encodeAnalyticsContext`/`decodeAnalyticsContext` (Task 7), `EXTENT_DEBOUNCE_MS` (Task 8), `AppRenderer`'s `initialAnalyticsContext`/`onAnalyticsContextChange` props (Task 9).
- Produces: reading `?ctx=` at mount hydrates the provider's initial state; every subsequent context change is written back to `?ctx=` with `setSearchParams(..., {replace: true})`, debounced by `EXTENT_DEBOUNCE_MS`.

- [ ] **Step 1: Write the failing tests**

Read `shell/src/pages/AppRuntimePage.test.tsx` first to match its existing `MemoryRouter`/`useAppConfig` mocking conventions, then add:

```tsx
test("hydrates the initial analytics context from the ctx URL param", async () => {
  const encoded = encodeAnalyticsContext({ timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {} });
  // ... render AppRuntimePage (via MemoryRouter with an initial entry
  // `/apps/9?ctx=${encoded}`) with a config that has interactions: "auto"
  // and a widget probing useAnalyticsContext() ...
  // assert the probe shows the decoded timeRange.
});

test("writes the analytics context back to the ctx URL param, debounced, with replace semantics", async () => {
  vi.useFakeTimers();
  // ... render AppRuntimePage with interactions: "auto", trigger a context
  // change (e.g. via a dateRangeFilter widget in the page), advance fake
  // timers past EXTENT_DEBOUNCE_MS, then assert location.search contains
  // an updated `ctx=` and that no new history entry was pushed (same
  // history.length before/after).
  vi.useRealTimers();
});
```

Write these two tests fully against the file's actual existing render helper (open it first) — do not introduce a second, divergent render setup.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx -t "ctx URL"`
Expected: FAIL — `AppRuntimePage` doesn't read or write `?ctx=` yet.

- [ ] **Step 3: Implement**

In `shell/src/pages/AppRuntimePage.tsx`, replace the imports:

```tsx
import { useNavigate } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useState, useEffect } from "react";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
```

with:

```tsx
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { EXTENT_DEBOUNCE_MS, type AnalyticsContextState } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useEffect, useMemo, useRef, useState } from "react";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
```

Inside the component body, right after `const navigate = useNavigate();`, add:

```tsx
  const [searchParams, setSearchParams] = useSearchParams();
  // Read once at mount ("au montage" per spec) — this component itself
  // writes ?ctx= back, so re-reading on every searchParams change would
  // create a feedback loop.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const initialAnalyticsContext = useMemo(() => decodeAnalyticsContext(searchParams.get("ctx")), []);
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (writeTimer.current) clearTimeout(writeTimer.current); }, []);

  function handleAnalyticsContextChange(state: AnalyticsContextState) {
    if (writeTimer.current) clearTimeout(writeTimer.current);
    writeTimer.current = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("ctx", encodeAnalyticsContext(state));
        return next;
      }, { replace: true });
    }, EXTENT_DEBOUNCE_MS);
  }
```

Replace the `<AppRenderer ... />` call:

```tsx
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
      />
```

with:

```tsx
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
        initialAnalyticsContext={initialAnalyticsContext}
        onAnalyticsContextChange={handleAnalyticsContextChange}
      />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Run the full shell unit suite and typecheck**

Run: `cd shell && npm run build && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "feat(shell): sérialise le contexte analytique dans l'URL runtime (?ctx=, replace, débounce) (SP-14b)"
```

---

### Task 18: E2E — cross-filter, extent reactivity, time range, URL restore, non-regression

**Files:**
- Create: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), the full feature stack from Tasks 1-17.

- [ ] **Step 1: Read the existing E2E conventions**

Read `shell/e2e/mocks.ts`, `shell/e2e/actions.spec.ts`, and `shell/e2e/datasets-shared.spec.ts` in full before writing — this task's tests must reuse `mockCore(page)` plus per-test `page.route(...)` overrides exactly like those two files, building the app through the real builder UI (not by injecting raw JSON configs).

- [ ] **Step 2: Write the 5 E2E scenarios**

Create `shell/e2e/analytics-context.spec.ts` with five `test(...)` blocks, each self-contained (own `mockCore(page)` call and routes):

1. **`"a chart click cross-filters a table on the same dataset, second click clears it"`** — Create a dataset (as in `datasets-shared.spec.ts` step 1) with `timeField` left empty. Create an app, add a data source bound to that dataset (twice — once for the chart, once for the table, mirroring "chart + table sur le même dataset" from spec §7), add a Chart widget (`categoryField` set to a column present in the mocked collection) and a Table widget, toggle "Interactions automatiques (cross-filter)" on. Save, go to runtime. Assert both widgets show all rows. Click a chart category (target the mocked `EChart`'s rendered SVG/canvas is not directly clickable in Playwright without ECharts' real DOM — instead, mock `**/collections/*/items*` responses to differ in row count depending on the request's query string, and assert the table narrows after the click via `page.locator("canvas").click(...)` at pixel coordinates producing a category hit, OR — more robustly — assert on the network request query string the table refetch sent (`page.waitForRequest` matching `nom=<value>`) rather than pixel-perfect canvas clicking). Click the same category again; assert the table request no longer carries the filter.

2. **`"map extent reactivity refetches a reactsToExtent dataset after the debounce"`** — Create a dataset with `reactsToExtent: true` (via `DatasetEditPage`'s new checkbox from Task 6). Build an app with a Map widget bound to that dataset and interactions "auto". At runtime, pan the map (`page.mouse.move`/`drag` on the MapLibre canvas) and assert (via `page.waitForRequest`) that a request eventually carries a `bbox` filter matching the new view — allow the ~500ms debounce with a generous Playwright timeout, no manual `page.waitForTimeout` shorter than the debounce.

3. **`"a date-range widget filters a timeField-bound dataset"`** — Create a dataset with `timeField` set (via Task 6's dropdown). Build an app with a `dateRangeFilter` widget and a Table widget on that dataset, interactions "auto". At runtime, fill both date inputs; assert (via `page.waitForRequest`) the table's request carries `<timeField>__gte=<from>&<timeField>__lte=<to>` (URL-encoded).

4. **`"the analytics context in the URL restores on reload"`** — Repeat scenario 1's or 3's setup; after triggering a cross-filter/time-range, read `page.url()`, assert it contains `?ctx=`; then `page.goto(capturedUrl)` (a fresh navigation) and assert the same filtered state is visible (e.g. the table still shows the narrowed row count) without re-clicking anything.

5. **`"an existing app without interactions never auto-filters on click"`** (non-regression) — Build the same chart+table-on-one-dataset app as scenario 1 but **leave "Interactions automatiques" off** (or omit `interactions` from the saved config entirely, simulating a pre-SP-14b app). At runtime, click the chart category and assert the table's request/row-count is **unchanged** — no automatic filter applied. Also assert any existing manually-wired `chart.categorySelected → table.setFilter` action (if configured via `ActionsPanel`, as in `actions.spec.ts`) still fires — proving the two channels coexist per spec §5.

- [ ] **Step 3: Run the new spec in isolation**

Run: `cd shell && npx playwright test e2e/analytics-context.spec.ts`
Expected: PASS (iterate on selectors/timing until green — this is real browser automation, so allow extra debugging time here versus the unit-test steps in earlier tasks).

- [ ] **Step 4: Run the full E2E suite to confirm no regression**

Run: `cd shell && npm run e2e`
Expected: PASS — all 18 pre-existing specs plus the new one, 19 specs total, green.

- [ ] **Step 5: Run the full shell suite one more time (build + unit + e2e) as a final gate**

Run: `cd shell && npm run build && npm run test && npm run e2e`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(shell): E2E cross-filter, emprise, plage temporelle, restauration URL, non-régression (SP-14b)"
```

---

## Self-Review Notes (for the plan author, not a task)

- **Spec coverage:** §2 (data model) → Task 1 (core), Task 4 (shell types), Task 6 (UI). §3 (core operators + bbox bug) → Tasks 2, 3, 5. §4 (`AnalyticsContextProvider`) → Tasks 7, 8, 9, 10, 11. §5 (per-widget wiring + CEL) → Tasks 12, 13, 14, 15, 16. §6 (URL) → Task 17. §7 (tests & risks) → the unit tests embedded in every task plus Task 18's E2E scenarios (1-5 map 1:1 to the spec's 5 scenarios); the risk table's "plusieurs widgets carte" (last-move-wins) is inherent to the single global `extent` state in `AnalyticsContextState` — no extra code needed, already the natural behavior of Task 8's design. The "cross-filter actif mais invisible" and "sur-ingénierie prématurée" risks are explicitly accepted non-goals (Global Constraints section) — no task addresses them, by design.
- **Two deliberate deviations from the design doc's literal wording**, both explained inline where they occur: (1) `originWidgetId` → `originSourceId`, storing a `DataSource.id` rather than a widget's layout `item.id` (Task 8's Interfaces note) — required because `DataContext.tsx` fetches per-`DataSource`, not per-widget-instance. (2) `configExpressionErrors.ts` gets a regression **test**, not new logic (Task 12) — `cel-js`'s `parse()` is syntax-only and already accepts any prefix.
- **Placeholder scan:** every step has literal code, exact file paths, and exact commands — the one intentionally "soft" spot is Task 18's E2E step 2 (bar-chart pixel click), flagged explicitly as needing iteration against the real Playwright run rather than a guessed selector, and Task 9 Step 6 / Task 17 Step 1, which point at reading an existing test file's conventions before writing new assertions (both existing files weren't fully quoted in this plan to avoid staleness — the instruction is to read them fresh, not a placeholder for missing design).
