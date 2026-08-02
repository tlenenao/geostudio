# SP-14f — Nouveaux types de graphiques (sankey, treemap, sunburst, funnel, histogramme binné) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 new modes to the existing `chart` widget — sankey, treemap, sunburst, funnel, and a server-computed binned histogram — completing the "widgets analytiques" list from the SP-14 roadmap entry, on the same "new modes of an existing widget" model as SP-14e.

**Architecture:** Core's `/collections/{id}/aggregate` gains two additive capabilities on `AggregateRequestBody`: `groupBy` widens from `str | None` to `str | list[str] | None` (a list produces tidy multi-column rows, one row per combination — what sankey and treemap/sunburst need), and a new `bins: int | None` triggers a two-query DuckDB binning path (MIN/MAX then `WIDTH_BUCKET`-style grouping) for the histogram. On the shell, `chartOption.ts` gains a new `encodings` field on `ChartProps` (used only by sankey and treemap/sunburst — funnel and histogram reuse the existing `categoryField`/`valueField`/`valueField`+`bins`), five new pure `buildOption` branches, and a new pure `resolveClickFilter` function that generalizes the existing click-to-cross-filter mechanic (including sankey's node-role ambiguity, resolved via a `_role` tag carried on each ECharts sankey node). `chart.tsx`'s `PropsPanel` and `handleClick` are thin wrappers around these pure functions, following the file's existing separation between pure option-building (`chartOption.ts`, fully unit-testable, no React/echarts import) and the React component (`chart.tsx`).

**Tech Stack:** FastAPI + DuckDB (core), React + TanStack Query + ECharts (shell), pytest / Vitest / Playwright.

## Global Constraints

- Every new capability (`groupBy` as a list, `bins`, `encodings`, the 5 new `chartType` values) is optional and absent by default — **zero behavior change** for the 10 existing chart types and all existing `AggregateRequestBody` callers.
- `encodings` is introduced **only** for `sankey` and `treemap`/`sunburst` — no retrofit onto bar/line/area/scatter/pie/doughnut/radar/heatmap/gauge/boxplot, which keep `categoryField`/`valueField` untouched.
- `funnel` reuses `categoryField`/`valueField` (structurally identical to `pie`); histogram reuses `valueField` (the field to bin) + new `bins` (default 10, bounded `1..100`).
- `bucket` (date-trunc) stays reserved to a single-field `groupBy` — combined with a multi-field `groupBy` it's a validation error. `split` (wide pivot) and multi-field `groupBy` are mutually exclusive (different output shapes) — also a validation error.
- Sankey v1 is a single hop (source→target only, no multi-stage chains). Treemap/sunburst hierarchy is capped at 3 levels.
- No cross-filter on histogram click (range-filtering is out of the current single-value cross-filter model) — the bars render but a click resolves to no filter.
- Docs/commit messages in French (conventional commits, e.g. `feat(core): …`), code/identifiers in English. Small commits, one subject each.
- Working branch: `dev`.

---

### Task 1: Core — `groupBy` widened to `str | list[str] | None`, validation

**Files:**
- Modify: `core/app/analytics/aggregate.py:26-34` (`AggregateRequestBody`), `core/app/analytics/aggregate.py:71-90` (`_validate_fields`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `AggregateRequestBody.groupBy: str | list[str] | None` (unchanged default `None`; a bare `str` behaves exactly as before). New `AggregateRequestBody.bins: int | None = None` field is declared here too (used starting Task 3) so the model only changes once. New helper `_groupby_fields(request: AggregateRequestBody) -> list[str]` — returns `[]` if `groupBy` is falsy, `[groupBy]` if it's a `str`, or the list itself if it's already a `list[str]`. Validation: duplicate fields in a `groupBy` list raise `UnknownAggregateField("groupBy", ...)`; `bucket` set with anything other than exactly one group-by field raises `UnknownAggregateField("bucket", ...)`; `split` set together with a multi-field `groupBy` raises `UnknownAggregateField("split", ...)`.

- [ ] **Step 1: Write the failing validation tests**

Append to `core/tests/test_analytics_aggregate.py`:

```python
def test_groupby_list_with_duplicate_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "region"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "groupBy"


def test_bucket_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], bucket="day")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bucket"


def test_split_with_multi_field_groupby_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "annee"], split="annee")
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "split"


def test_groupby_list_with_unknown_field_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy=["region", "inconnu"])
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "groupBy"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "duplicate or multi_field or unknown_field" -v`
Expected: FAIL (model doesn't accept a list yet / no validation exists)

- [ ] **Step 3: Widen the model and add validation**

In `core/app/analytics/aggregate.py`, replace the `AggregateRequestBody` class (lines 26-34):

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    bucket: Literal["day", "week", "month"] | None = None
    bins: int | None = None
```

Add the helper right after `_valid_column_names` (after line 68):

```python
def _groupby_fields(request: AggregateRequestBody) -> list[str]:
    if not request.groupBy:
        return []
    return request.groupBy if isinstance(request.groupBy, list) else [request.groupBy]
```

Replace `_validate_fields` (lines 71-90) with:

```python
def _validate_fields(request: AggregateRequestBody, table_info) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    fields = _groupby_fields(request)
    if len(fields) != len(set(fields)):
        raise UnknownAggregateField("groupBy", "duplicate field in groupBy")
    for f in fields:
        check(f, "groupBy")

    if request.bucket is not None and len(fields) != 1:
        raise UnknownAggregateField("bucket", "bucket requires a single-field groupBy")
    if request.split and len(fields) > 1:
        raise UnknownAggregateField("split", "split cannot combine with a multi-field groupBy")

    check(request.split, "split")
    check(request.field, "field")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
    for raw_name in request.filters:
        field_name, _ = _split_filter_key(raw_name)
        check(field_name, f"filters.{raw_name}")
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "duplicate or multi_field or unknown_field" -v`
Expected: PASS

- [ ] **Step 5: Run the full core suite for non-regression**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`
Expected: PASS — all existing tests (single-field `groupBy`, `bucket`, `split`, filters, bbox) stay green.

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): accept groupBy as a list of fields on /aggregate, with validation (SP-14f)"
```

---

### Task 2: Core — multi-field `groupBy` produces tidy rows

**Files:**
- Modify: `core/app/analytics/aggregate.py:170-177` (`_pivot_measures`, add `_pivot_multi_measures` next to it), `core/app/analytics/aggregate.py:203-232` (`run_collection_aggregate`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: `_groupby_fields` from Task 1.
- Produces: `run_collection_aggregate` returns `category_key: str | list[str]` — a `list[str]` (the group-by fields, in order) when `groupBy` has 2-3 fields; unchanged `str` otherwise. Rows are tidy: one dict per combination, one key per group-by field (real column name) + one key per measure label.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_analytics_aggregate.py`:

```python
def test_two_field_groupby_produces_tidy_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 12, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy=["region", "annee"], agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == ["region", "annee"]
    assert sorted(rows, key=lambda r: (r["region"], r["annee"])) == [
        {"region": "Nord", "annee": "2025", "value": 10},
        {"region": "Nord", "annee": "2026", "value": 12},
        {"region": "Sud", "annee": "2025", "value": 5},
    ]


def test_three_field_groupby_produces_tidy_rows(tmp_path, conn):
    # Réutilise "pop" comme 3e dimension (valeurs distinctes = niveau de hiérarchie),
    # TABLE_INFO n'a que 3 colonnes non-géométrie disponibles pour ce test.
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1),
    ])
    request = AggregateRequestBody(groupBy=["region", "annee", "pop"], agg="count")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == ["region", "annee", "pop"]
    assert sorted(rows, key=lambda r: r["pop"]) == [
        {"region": "Nord", "annee": "2025", "pop": 10, "value": 1},
        {"region": "Nord", "annee": "2025", "pop": 20, "value": 1},
    ]


def test_multi_field_groupby_with_multiple_measures(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(
        groupBy=["region", "annee"],
        measures=[AggregateMeasure(agg="sum", field="pop", label="total"),
                  AggregateMeasure(agg="count", label="nb")],
    )

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "annee": "2025", "total": 30, "nb": 2},
        {"region": "Sud", "annee": "2025", "total": 5, "nb": 1},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "tidy_rows or multiple_measures" -v`
Expected: FAIL (`_qi()` / `cat_expr` construction breaks on a `list` today)

- [ ] **Step 3: Add `_pivot_multi_measures` and the multi-field branch**

Add right after `_pivot_measures` (after line 177) in `core/app/analytics/aggregate.py`:

```python
def _pivot_multi_measures(sql_rows: list[dict], *, fields: list[str], measures: list[AggregateMeasure]) -> list[dict]:
    out = []
    for r in sql_rows:
        row = {f: r[f] for f in fields}
        for i, m in enumerate(measures):
            row[_measure_label(m)] = r[f"m{i}"]
        out.append(row)
    return out
```

Replace `run_collection_aggregate` (lines 203-232) with:

```python
def run_collection_aggregate(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info, request: AggregateRequestBody,
) -> tuple[str | list[str], list[dict]]:
    fields = _groupby_fields(request)
    category_key: str | list[str] = fields if len(fields) > 1 else (fields[0] if fields else "group")
    _validate_fields(request, table_info)

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)

    if len(fields) > 1:
        measures = _measures_for(request)
        measure_cols = ", ".join(f"{_agg_expr(m.agg, m.field)} AS m{i}" for i, m in enumerate(measures))
        group_cols = ", ".join(_qi(f) for f in fields)
        sql = f"{dedup_cte} SELECT {group_cols}, {measure_cols} FROM live {where_sql} GROUP BY {group_cols}"
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_multi_measures(sql_rows, fields=fields, measures=measures)

    single_field = fields[0] if fields else None
    if request.bucket:
        cat_expr = f"DATE_TRUNC({_sql_lit(request.bucket)}, TRY_CAST({_qi(single_field)} AS TIMESTAMP))"
    else:
        cat_expr = _qi(single_field) if single_field else "'Total'"

    if request.split:
        agg_sql = _agg_expr(request.agg, request.field)
        sql = (
            f"{dedup_cte} SELECT {cat_expr} AS __cat, {_qi(request.split)} AS __split, "
            f"{agg_sql} AS __val FROM live {where_sql} GROUP BY __cat, __split"
        )
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_split(sql_rows, category_key=str(category_key))

    measures = _measures_for(request)
    measure_cols = ", ".join(f"{_agg_expr(m.agg, m.field)} AS m{i}" for i, m in enumerate(measures))
    sql = f"{dedup_cte} SELECT {cat_expr} AS __cat, {measure_cols} FROM live {where_sql} GROUP BY __cat"
    sql_rows = _fetch_rows(conn, sql, where_params)
    return category_key, _pivot_measures(sql_rows, category_key=str(category_key), measures=measures)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k "tidy_rows or multiple_measures" -v`
Expected: PASS

- [ ] **Step 5: Run the full core suite for non-regression**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -v`
Expected: PASS — all existing single-field tests untouched (same branch, `category_key: str` as before).

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): multi-field groupBy produces tidy rows on /aggregate (SP-14f)"
```

---

### Task 3: Core — server-side binned histogram (`bins`)

**Files:**
- Modify: `core/app/analytics/aggregate.py` (`_validate_fields`, add `_run_binned_histogram`, `run_collection_aggregate`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: `request.bins: int | None` (Task 1), `request.field`.
- Produces: when `bins` is set, `run_collection_aggregate` returns rows shaped `{"bucketIndex": int, "bucketStart": float, "bucketEnd": float, "count": int}`, one per non-empty bin, ordered by `bucketIndex`. `category_key` in this mode is `"bins"` (a fixed label, not consumed by the shell for id-building since the histogram doesn't need a categorical id — see Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_analytics_aggregate.py`:

```python
def test_bins_produces_equal_width_buckets(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 1, lsn=1), _row(2, "Nord", "2025", 2, lsn=1),
        _row(3, "Nord", "2025", 9, lsn=1), _row(4, "Nord", "2025", 10, lsn=1),
    ])
    request = AggregateRequestBody(field="pop", bins=3)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    # pop in [1, 10], 3 bins of width 3 → [1,4), [4,7), [7,10] (last bin absorbs the max via LEAST clamp)
    by_index = {r["bucketIndex"]: r["count"] for r in rows}
    assert by_index == {0: 2, 2: 2}  # pop 1,2 → bin 0 ; pop 9,10 → bin 2 (clamped) ; bin 1 empty, absent


def test_bins_on_a_constant_field_returns_one_bucket(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 5, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(field="pop", bins=4)

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 5.0, "bucketEnd": 5.0, "count": 2}]


def test_bins_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bins"


def test_bins_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bins"


def test_bins_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 101):
        request = AggregateRequestBody(field="pop", bins=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
                table_info=TABLE_INFO, request=request,
            )
        assert exc.value.field == "bins"


def test_bins_narrowed_by_attribute_filter(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 1, lsn=1), _row(2, "Sud", "2025", 9, lsn=1),
    ])
    request = AggregateRequestBody(field="pop", bins=2, filters={"region": "Nord"})

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"bucketIndex": 0, "bucketStart": 1.0, "bucketEnd": 1.0, "count": 1}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bins -v`
Expected: FAIL (`bins` not yet validated/implemented)

- [ ] **Step 3: Add bins validation**

In `_validate_fields` (edited in Task 1), add before the final `bbox` check:

```python
    if request.bins is not None:
        if request.field is None:
            raise UnknownAggregateField("bins", "bins requires a field")
        if fields:
            raise UnknownAggregateField("bins", "bins cannot combine with groupBy")
        if not (1 <= request.bins <= 100):
            raise UnknownAggregateField("bins", "bins must be between 1 and 100")
```

- [ ] **Step 4: Add `_run_binned_histogram` and wire it into `run_collection_aggregate`**

Add next to `_pivot_multi_measures` in `core/app/analytics/aggregate.py`:

```python
def _run_binned_histogram(
    conn, *, dedup_cte: str, where_sql: str, where_params: list, field: str, bins: int,
) -> list[dict]:
    field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    minmax_sql = f"{dedup_cte} SELECT MIN({field_expr}) AS lo, MAX({field_expr}) AS hi FROM live {where_sql}"
    minmax_rows = _fetch_rows(conn, minmax_sql, where_params)
    lo = minmax_rows[0]["lo"] if minmax_rows else None
    hi = minmax_rows[0]["hi"] if minmax_rows else None
    if lo is None or hi is None:
        return []

    not_null_clause = f"{_qi(field)} IS NOT NULL"
    full_where = f"{where_sql} AND {not_null_clause}" if where_sql else f"WHERE {not_null_clause}"

    if lo == hi:
        sql = f"{dedup_cte} SELECT COUNT(*) AS __val FROM live {full_where}"
        rows = _fetch_rows(conn, sql, where_params)
        return [{"bucketIndex": 0, "bucketStart": lo, "bucketEnd": hi, "count": rows[0]["__val"]}]

    width = (hi - lo) / bins
    bucket_expr = f"LEAST(? - 1, CAST(FLOOR(({field_expr} - ?) / ?) AS INTEGER))"
    sql = (
        f"{dedup_cte} SELECT {bucket_expr} AS __bucket, COUNT(*) AS __val "
        f"FROM live {full_where} GROUP BY __bucket ORDER BY __bucket"
    )
    params = [bins, lo, width, *where_params]
    rows = _fetch_rows(conn, sql, params)
    return [
        {
            "bucketIndex": int(r["__bucket"]),
            "bucketStart": lo + r["__bucket"] * width,
            "bucketEnd": lo + (r["__bucket"] + 1) * width,
            "count": r["__val"],
        }
        for r in rows
    ]
```

In `run_collection_aggregate`, insert right after the `where_sql, where_params = _build_where(...)` line, before the `if len(fields) > 1:` branch:

```python
    if request.bins is not None:
        rows = _run_binned_histogram(
            conn, dedup_cte=dedup_cte, where_sql=where_sql, where_params=where_params,
            field=request.field, bins=request.bins,
        )
        return "bucketIndex", rows
```

(`"bucketIndex"` is a real column present on every row this branch returns — unlike a fixed `"bins"` literal, this lets the shell's `statRowId` (Task 4) derive a correct, unique per-row id via the existing single-field path, with no histogram-specific case needed.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bins -v`
Expected: PASS

- [ ] **Step 6: Run the full core suite for non-regression**

Run: `cd core && uv run pytest -v`
Expected: PASS — full suite (606+ existing + new tests from Tasks 1-3).

- [ ] **Step 7: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): server-side binned histogram via bins param on /aggregate (SP-14f)"
```

---

### Task 4: Shell — `itemClient` passes `groupBy` arrays and `bins` through, builds composite ids

**Files:**
- Modify: `shell/src/api/itemClient.ts:40` (`STAT_KEYS`), `shell/src/api/itemClient.ts:49-73` (`buildAggregateBody`), `shell/src/api/itemClient.ts:619-630` (`queryDataSource`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `buildAggregateBody` forwards `query.groupBy` as a `string[]` when it's an array (unchanged `string` otherwise), and forwards `query.bins` as a `number`. New helper `statRowId(row: Record<string, unknown>, categoryKey: string | string[]): string` — joins multi-field values with `"|"` for a stable per-row id; unchanged single-field behavior otherwise.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("queryDataSource sends an array groupBy as-is in the aggregate request body", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: ["region", "annee"], rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "count" },
  });
  expect(posted!.groupBy).toEqual(["region", "annee"]);
});

test("queryDataSource builds a composite id when categoryKey is a multi-field array", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: ["region", "annee"],
        rows: [{ region: "Nord", annee: "2025", value: 10 }],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord|2025", properties: { region: "Nord", annee: "2025", value: 10 } },
  ]);
});

test("queryDataSource sends a bins query key as body.bins, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "bucketIndex", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { field: "pop", bins: 5 },
  });
  expect(posted!.bins).toBe(5);
  expect(posted!.filters).toBeUndefined();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "groupBy|composite id|bins query"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/api/itemClient.ts`, replace line 40:

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox", "bucket", "bins"]);
```

Replace `buildAggregateBody` (lines 49-73):

```ts
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

// Multi-field groupBy responses carry no single categorical key — this joins
// the group columns' values into a stable per-row id (single-field case
// unchanged: same as `String(row[categoryKey])` today).
function statRowId(row: Record<string, unknown>, categoryKey: string | string[]): string {
  if (Array.isArray(categoryKey)) return categoryKey.map((k) => String(row[k] ?? "")).join("|");
  return String(row[categoryKey] ?? "");
}
```

In `queryDataSource` (lines 626-630), replace:

```ts
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${resolved.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
      }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS — new tests plus full existing file green.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient forwards multi-field groupBy and bins to /aggregate (SP-14f)"
```

---

### Task 5: Shell — `DataSourcePanel` supports a comma-separated multi-field `groupBy` and a `bins` field

**Files:**
- Modify: `shell/src/builder/DataSourcePanel.tsx:76-93`
- Test: `shell/src/builder/DataSourcePanel.test.tsx`

**Interfaces:**
- Produces: new pure helper `parseGroupBy(raw: string): string | string[]` (exported for the test, or kept module-private and covered through the component test below — kept module-private here, consistent with the file's existing lack of exports beyond `DataSourcePanel`). Typing a value with no comma keeps `query.groupBy` a plain `string` (byte-for-byte unchanged behavior); typing a comma-separated value sets it to a `string[]`. New "Nombre de classes" numeric input writes `query.bins`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/DataSourcePanel.test.tsx` (needs `fireEvent` alongside the existing `render`/`screen`/`within` import):

```tsx
test("a comma-separated group-by becomes a string array; a single field stays a string", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} }];
  const onChange = vi.fn();
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Grouper par (source d1)"), { target: { value: "origin,destination" } });
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toEqual(["origin", "destination"]);

  const withArray: DataSource[] = [{ ...sources[0], query: { groupBy: ["origin", "destination"] } }];
  rerender(<DataSourcePanel sources={withArray} onChange={onChange} />);
  expect(screen.getByLabelText("Grouper par (source d1)")).toHaveValue("origin,destination");
});

test("edits the histogram bin count on a statistics source", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nombre de classes (source d1)"), "8");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.bins).toBe(8);
});
```

Update the file's import line to add `fireEvent`:

```tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx -t "comma-separated|bin count"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/builder/DataSourcePanel.tsx`, add a module-level helper right after the `type Measure = ...` line:

```tsx
// A single field ("region") is passed through unchanged; a comma-separated
// value ("origin,destination") becomes a string[] — the multi-field tidy
// groupBy that sankey/treemap/sunburst need (SP-14f).
function parseGroupBy(raw: string): string | string[] {
  const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
  return parts.length > 1 ? parts : raw;
}

function groupByDisplayValue(groupBy: unknown): string {
  return Array.isArray(groupBy) ? groupBy.join(",") : String(groupBy ?? "");
}
```

Replace the "Grouper par" input (lines 76-78) with:

```tsx
                <input aria-label={`Grouper par (source ${s.id})`} placeholder="grouper par (axe X, virgule = plusieurs niveaux)"
                  className={inputCls}
                  value={groupByDisplayValue(s.query.groupBy)}
                  onChange={(e) => patchQuery(s.id, { groupBy: parseGroupBy(e.target.value) })} />
```

Add a "Nombre de classes" numeric input right after the "Champ agrégé" input (after line 94, still inside the `<div className="flex gap-1">` sibling block, as its own line below that div):

```tsx
                <input aria-label={`Nombre de classes (source ${s.id})`} type="number" min={1} max={100}
                  placeholder="classes (histogramme)" className={inputCls}
                  value={String(s.query.bins ?? "")}
                  onChange={(e) => patchQuery(s.id, { bins: e.target.value ? Number(e.target.value) : undefined })} />
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: PASS — new tests plus full existing file green (existing "edits a statistics source's group-by and split" test still passes: typing a single char has no comma, `parseGroupBy` returns it unchanged).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx
git commit -m "feat(shell): DataSourcePanel supports multi-field groupBy and a histogram bin count (SP-14f)"
```

---

### Task 6: Shell — `chartOption.ts`: `encodings`/`bins` types, funnel and histogram

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts:6-20` (`ChartProps`), `shell/src/builder/widgets/chartOption.ts:127-151` (add branches before the fallback bar/line/area/scatter block)
- Test: `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Produces: `ChartProps.encodings?: { source?: string; target?: string; levels?: string[]; value?: string }` and `ChartProps.bins?: number`. `buildOption` handles `chartType === "funnel"` (reuses `categoryField`/`valueField`) and `chartType === "histogram"` (reads `bucketStart`/`bucketEnd`/`count` off each row — the shape `_run_binned_histogram` (Task 3) produces).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
const histogramRows: DataRecord[] = [
  { id: "0", properties: { bucketIndex: 0, bucketStart: 0, bucketEnd: 5, count: 3 } },
  { id: "2", properties: { bucketIndex: 2, bucketStart: 10, bucketEnd: 15, count: 7 } },
];

test("funnel builds one funnel series from category/value fields", () => {
  const funnelRows: DataRecord[] = [
    { id: "1", properties: { stage: "Visite", value: 100 } },
    { id: "2", properties: { stage: "Panier", value: 40 } },
  ];
  const opt = buildOption({ chartType: "funnel", categoryField: "stage", valueField: "value" }, funnelRows);
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("funnel");
  expect(series(opt)[0].data).toEqual([{ name: "Visite", value: 100 }, { name: "Panier", value: 40 }]);
});

test("histogram renders one bar series labeled by bucket bounds", () => {
  const opt = buildOption({ chartType: "histogram" }, histogramRows);
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("bar");
  expect(series(opt)[0].data).toEqual([3, 7]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["0–5", "10–15"]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "funnel|histogram"`
Expected: FAIL (unknown chart types fall through to the default bar/line branch, wrong shape)

- [ ] **Step 3: Implement**

In `shell/src/builder/widgets/chartOption.ts`, replace the `ChartProps` type (lines 6-20):

```ts
export type ChartProps = {
  dataSourceId?: string;
  chartType?: string; // bar|line|area|scatter|pie|doughnut|radar|heatmap|gauge|boxplot|sankey|treemap|sunburst|funnel|histogram
  categoryField?: string;
  valueField?: string; // measure key for pie/gauge/funnel/histogram (defaults to first series)
  stack?: boolean;
  legend?: boolean;
  zoom?: boolean;
  xAxisType?: string; // category|value|time|log
  yAxisType?: string; // value|log|category
  yAxisFormat?: string; // any non-empty value → grouped number formatting
  yAxisUnit?: string;
  title?: string;
  advancedOption?: string; // raw ECharts option JSON, deep-merged last
  // Field-role mapping used only by sankey and treemap/sunburst — every
  // other chart type keeps categoryField/valueField (SP-14f §3).
  encodings?: { source?: string; target?: string; levels?: string[]; value?: string };
  bins?: number; // histogram bin count, default 10
};
```

Add a small formatting helper right after `valueFormatter` (after line 59):

```ts
function round2(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(n);
}
```

In `buildOption`, insert two new branches right before the `// bar | line | area | scatter` fallback comment (before line 136):

```ts
  if (type === "funnel") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      series: [{
        type: "funnel",
        data: rows.map((row) => ({ name: String(row[catKey] ?? ""), value: num(row[valueKey]) })),
      }],
    });
  }

  if (type === "histogram") {
    const labels = rows.map((row) => `${round2(Number(row.bucketStart))}–${round2(Number(row.bucketEnd))}`);
    const counts = rows.map((row) => num(row.count));
    return finalize(props, {
      ...base,
      xAxis: { type: "category", data: labels },
      yAxis,
      series: [{ type: "bar", name: "Effectif", data: counts }],
    });
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS — new tests plus full existing file green.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chartOption gains funnel and server-binned histogram (SP-14f)"
```

---

### Task 7: Shell — `chartOption.ts`: sankey (with node-role tagging)

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts` (add a branch in `buildOption`)
- Test: `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Produces: `buildOption` handles `chartType === "sankey"`, reading `props.encodings.source`/`target`/`value`. Each generated node carries a non-visual `_role: "source" | "target"` field — a name seen as a source in any row is tagged `"source"` (source takes priority over target when a value appears as both, a deliberate simplification since v1 sankey is single-hop and this ambiguity is rare). `resolveClickFilter` (Task 9) reads this tag to disambiguate which encoding a clicked node's name maps to.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
const flows: DataRecord[] = [
  { id: "1", properties: { origin: "Paris", destination: "Lyon", value: 10 } },
  { id: "2", properties: { origin: "Paris", destination: "Marseille", value: 5 } },
  { id: "3", properties: { origin: "Lyon", destination: "Marseille", value: 3 } }, // "Lyon" is both a destination and an origin
];

test("sankey builds nodes (tagged by role) and links from source/target/value encodings", () => {
  const opt = buildOption(
    { chartType: "sankey", encodings: { source: "origin", target: "destination", value: "value" } }, flows,
  );
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("sankey");
  expect(series(opt)[0].links).toEqual([
    { source: "Paris", target: "Lyon", value: 10 },
    { source: "Paris", target: "Marseille", value: 5 },
    { source: "Lyon", target: "Marseille", value: 3 },
  ]);
  const nodesByName = Object.fromEntries(series(opt)[0].data.map((n: { name: string; _role: string }) => [n.name, n._role]));
  expect(nodesByName.Paris).toBe("source");
  expect(nodesByName.Marseille).toBe("target");
  // Lyon is both a target (row 1) and a source (row 3) — source wins (documented tie-break).
  expect(nodesByName.Lyon).toBe("source");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t sankey`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/builder/widgets/chartOption.ts`, add right after the `histogram` branch added in Task 6:

```ts
  if (type === "sankey") {
    const sourceField = props.encodings?.source ?? "";
    const targetField = props.encodings?.target ?? "";
    const valueKey = props.encodings?.value || seriesKeys.find((k) => k !== sourceField && k !== targetField) || "";
    const sourceNames = new Set(rows.map((row) => String(row[sourceField] ?? "")));
    const allNames = new Set<string>();
    rows.forEach((row) => {
      allNames.add(String(row[sourceField] ?? ""));
      allNames.add(String(row[targetField] ?? ""));
    });
    const nodes = [...allNames].map((name) => ({ name, _role: sourceNames.has(name) ? "source" : "target" }));
    const links = rows.map((row) => ({
      source: String(row[sourceField] ?? ""), target: String(row[targetField] ?? ""), value: num(row[valueKey]),
    }));
    return finalize(props, { ...base, series: [{ type: "sankey", data: nodes, links }] });
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t sankey`
Expected: PASS

- [ ] **Step 5: Run the full file for non-regression**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chartOption gains sankey with role-tagged nodes (SP-14f)"
```

---

### Task 8: Shell — `chartOption.ts`: treemap/sunburst hierarchy

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts` (add `buildHierarchy` + a branch in `buildOption`)
- Test: `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Produces: `buildOption` handles `chartType === "treemap" | "sunburst"`, reading `props.encodings.levels` (1-3 field names, root→leaf) and `props.encodings.value`. New pure helper `buildHierarchy(rows: Row[], levels: string[], valueKey: string): TreeNode[]` where `TreeNode = { name: string; value?: number; children?: TreeNode[] }` — leaf values sum bottom-up into every ancestor.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
const sales: DataRecord[] = [
  { id: "1", properties: { region: "Nord", city: "Lille", value: 10 } },
  { id: "2", properties: { region: "Nord", city: "Reims", value: 5 } },
  { id: "3", properties: { region: "Sud", city: "Nice", value: 7 } },
];

test("treemap builds a hierarchy from levels, summing values bottom-up", () => {
  const opt = buildOption(
    { chartType: "treemap", encodings: { levels: ["region", "city"], value: "value" } }, sales,
  );
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("treemap");
  const tree = series(opt)[0].data as { name: string; value: number; children?: { name: string; value: number }[] }[];
  const nord = tree.find((n) => n.name === "Nord")!;
  expect(nord.value).toBe(15);
  expect(nord.children).toEqual([{ name: "Lille", value: 10 }, { name: "Reims", value: 5 }]);
  const sud = tree.find((n) => n.name === "Sud")!;
  expect(sud.value).toBe(7);
});

test("sunburst uses the same hierarchy builder as treemap", () => {
  const opt = buildOption({ chartType: "sunburst", encodings: { levels: ["region"], value: "value" } }, sales);
  expect(series(opt)[0].type).toBe("sunburst");
  const tree = series(opt)[0].data as { name: string; value: number }[];
  expect(tree.find((n) => n.name === "Nord")?.value).toBe(15);
});

test("treemap groups missing intermediate-level values under a literal placeholder node", () => {
  const withGap: DataRecord[] = [
    { id: "1", properties: { region: "Nord", city: null, value: 4 } },
    { id: "2", properties: { region: "Nord", city: "Lille", value: 6 } },
  ];
  const opt = buildOption({ chartType: "treemap", encodings: { levels: ["region", "city"], value: "value" } }, withGap);
  const nord = (series(opt)[0].data as { name: string; children?: { name: string; value: number }[] }[]).find((n) => n.name === "Nord")!;
  expect(nord.children).toEqual(expect.arrayContaining([{ name: "—", value: 4 }, { name: "Lille", value: 6 }]));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "treemap|sunburst"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/builder/widgets/chartOption.ts`, add a `TreeNode` type and `buildHierarchy` helper right after `Row`/`isPlainObject` (near the top, after line 22):

```ts
type TreeNode = { name: string; value?: number; children?: TreeNode[] };

// Builds a root→leaf hierarchy from tidy rows: one path per row through
// `levels`, leaf values accumulated then summed bottom-up into every ancestor.
function buildHierarchy(rows: Row[], levels: string[], valueKey: string): TreeNode[] {
  const roots: TreeNode[] = [];
  const index = new Map<string, TreeNode>();
  for (const row of rows) {
    let path = "";
    let siblings = roots;
    let node: TreeNode | undefined;
    for (const level of levels) {
      const name = String(row[level] ?? "—");
      path = `${path}/${name}`;
      node = index.get(path);
      if (!node) {
        node = { name };
        index.set(path, node);
        siblings.push(node);
      }
      node.children ??= [];
      siblings = node.children;
    }
    if (node) node.value = (node.value ?? 0) + num(row[valueKey]);
  }
  const sumUp = (node: TreeNode): number => {
    if (!node.children || node.children.length === 0) {
      delete node.children;
      return node.value ?? 0;
    }
    node.value = node.children.reduce((acc, c) => acc + sumUp(c), 0);
    return node.value;
  };
  roots.forEach(sumUp);
  return roots;
}
```

In `buildOption`, add right after the `sankey` branch (Task 7):

```ts
  if (type === "treemap" || type === "sunburst") {
    const levels = props.encodings?.levels ?? [];
    const valueKey = props.encodings?.value || seriesKeys.find((k) => !levels.includes(k)) || "";
    const tree = buildHierarchy(rows, levels, valueKey);
    return finalize(props, { ...base, series: [{ type, data: tree }] });
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "treemap|sunburst"`
Expected: PASS

- [ ] **Step 5: Run the full file for non-regression**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chartOption gains treemap/sunburst hierarchy building (SP-14f)"
```

---

### Task 9: Shell — `chartOption.ts`: `resolveClickFilter` (generalized cross-filter resolution)

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts` (add `ClickParams` type + `resolveClickFilter`)
- Test: `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Produces: `export type ClickParams = { name?: string; dataType?: string; data?: Record<string, unknown>; treePathInfo?: { name: string }[] }` and `export function resolveClickFilter(chartType: string, props: ChartProps, params: ClickParams): { field: string; value: string } | null`. This is the function `chart.tsx`'s `handleClick` calls in Task 11 — it must not import React or echarts (kept in `chartOption.ts` alongside the other pure functions).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
test("resolveClickFilter: default types (bar/pie/...) resolve categoryField, like today", () => {
  expect(resolveClickFilter("bar", { categoryField: "region" }, { name: "Nord" })).toEqual({ field: "region", value: "Nord" });
  expect(resolveClickFilter("bar", {}, { name: "Nord" })).toBeNull(); // no categoryField → no filter, unchanged
});

test("resolveClickFilter: funnel resolves categoryField same as pie/bar", () => {
  expect(resolveClickFilter("funnel", { categoryField: "stage" }, { name: "Panier" })).toEqual({ field: "stage", value: "Panier" });
});

test("resolveClickFilter: histogram never resolves a filter", () => {
  expect(resolveClickFilter("histogram", { categoryField: "x" }, { name: "0–5" })).toBeNull();
});

test("resolveClickFilter: treemap/sunburst resolve the deepest clicked level", () => {
  const props = { chartType: "treemap", encodings: { levels: ["region", "city"] } };
  // Clicking a leaf: treePathInfo has 2 entries (region, city) → depth 1 → levels[1] = "city".
  expect(resolveClickFilter("treemap", props, { name: "Lille", treePathInfo: [{ name: "Nord" }, { name: "Lille" }] }))
    .toEqual({ field: "city", value: "Lille" });
  // Clicking a root: treePathInfo has 1 entry → depth 0 → levels[0] = "region".
  expect(resolveClickFilter("treemap", props, { name: "Nord", treePathInfo: [{ name: "Nord" }] }))
    .toEqual({ field: "region", value: "Nord" });
});

test("resolveClickFilter: sankey resolves source or target depending on the clicked node's role, ignores edge clicks", () => {
  const props = { chartType: "sankey", encodings: { source: "origin", target: "destination" } };
  expect(resolveClickFilter("sankey", props, { dataType: "node", name: "Paris", data: { _role: "source" } }))
    .toEqual({ field: "origin", value: "Paris" });
  expect(resolveClickFilter("sankey", props, { dataType: "node", name: "Lyon", data: { _role: "target" } }))
    .toEqual({ field: "destination", value: "Lyon" });
  expect(resolveClickFilter("sankey", props, { dataType: "edge", name: "Paris" })).toBeNull();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t resolveClickFilter`
Expected: FAIL (`resolveClickFilter` doesn't exist)

- [ ] **Step 3: Implement**

Add to `shell/src/builder/widgets/chartOption.ts`, after `buildOption` and before `buildCompareOption`:

```ts
export type ClickParams = {
  name?: string;
  dataType?: string;
  data?: Record<string, unknown>;
  treePathInfo?: { name: string }[];
};

// Generalizes the click→cross-filter mapping across all chart types. Default
// (bar/line/pie/.../funnel): unchanged categoryField behavior. Histogram:
// never resolves (range-filtering is out of the single-value cross-filter
// model). Treemap/sunburst: the deepest clicked hierarchy level. Sankey: the
// clicked node's role (tagged _role in buildOption, see the sankey branch)
// disambiguates whether it maps to encodings.source or encodings.target.
export function resolveClickFilter(
  chartType: string, props: ChartProps, params: ClickParams,
): { field: string; value: string } | null {
  if (chartType === "histogram") return null;

  if (chartType === "sankey") {
    if (params.dataType !== "node" || params.name == null) return null;
    const role = params.data?._role as "source" | "target" | undefined;
    const field = role === "target" ? props.encodings?.target : props.encodings?.source;
    if (!field) return null;
    return { field, value: String(params.name) };
  }

  if (chartType === "treemap" || chartType === "sunburst") {
    const levels = props.encodings?.levels ?? [];
    if (!levels.length || params.name == null) return null;
    const depth = Math.min(Math.max((params.treePathInfo?.length ?? 1) - 1, 0), levels.length - 1);
    const field = levels[depth];
    if (!field) return null;
    return { field, value: String(params.name) };
  }

  const field = props.categoryField;
  if (!field || params.name == null) return null;
  return { field, value: String(params.name) };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t resolveClickFilter`
Expected: PASS

- [ ] **Step 5: Run the full file for non-regression**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS — all tests from Tasks 6-9 plus the pre-existing suite green.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): resolveClickFilter generalizes click-to-cross-filter across chart types (SP-14f)"
```

---

### Task 10: Shell — `EChart.tsx`: register `SunburstChart`, widen the click param type

**Files:**
- Modify: `shell/src/builder/EChart.tsx:4-27` (imports + `echarts.use`), `shell/src/builder/EChart.tsx:40-53` (`onClick` type + handler)
- Test: `shell/src/builder/EChart.test.tsx` (create if it doesn't already exist — check first with `find shell/src/builder -iname "EChart.test.tsx"`)

**Interfaces:**
- Produces: `EChart`'s `onClick` prop type widens to `(params: { name?: string; value?: unknown; dataType?: string; data?: Record<string, unknown>; treePathInfo?: { name: string }[] }) => void` — a strict superset of today's type, so every existing caller (bar/pie click handlers) keeps compiling unchanged. `SunburstChart` becomes renderable.

- [ ] **Step 1: Check whether an EChart test file exists**

Run: `find /home/lenen/projets/geostudio/shell/src/builder -iname "EChart.test.tsx"`

If it exists, read it first and add the new test alongside the existing ones using the same render/mock conventions. If it doesn't exist, create it fresh with the content below.

- [ ] **Step 2: Write the failing test**

`shell/src/builder/EChart.test.tsx` (new test, appended if the file already exists):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { test, expect } from "vitest";
import { EChart } from "./EChart";

test("renders a sunburst option without throwing (SunburstChart must be registered)", () => {
  const { getByTestId } = render(
    <EChart option={{ series: [{ type: "sunburst", data: [{ name: "A", value: 1 }] }] }} />,
  );
  expect(getByTestId("echart")).toHaveAttribute("data-chart-type", "sunburst");
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/EChart.test.tsx -t sunburst`
Expected: FAIL (`echarts.init(...).setOption(...)` throws — `SunburstChart` component not registered, "series.sunburst" unknown)

- [ ] **Step 4: Implement**

In `shell/src/builder/EChart.tsx`, replace the `echarts/charts` import (lines 4-8):

```ts
import {
  BarChart, LineChart, PieChart, ScatterChart, RadarChart,
  HeatmapChart, GaugeChart, BoxplotChart, CandlestickChart,
  FunnelChart, SankeyChart, TreemapChart, SunburstChart,
} from "echarts/charts";
```

Replace the `echarts.use([...])` call (lines 19-27):

```ts
echarts.use([
  BarChart, LineChart, PieChart, ScatterChart, RadarChart,
  HeatmapChart, GaugeChart, BoxplotChart, CandlestickChart,
  FunnelChart, SankeyChart, TreemapChart, SunburstChart,
  TooltipComponent, LegendComponent, GridComponent, DataZoomComponent,
  VisualMapComponent, TitleComponent, ToolboxComponent, PolarComponent,
  DatasetComponent, MarkLineComponent, MarkAreaComponent,
  CanvasRenderer,
]);
```

Widen the `onClick` type on `EChart`'s props (line 40-42) and the click handler (line 53):

```tsx
export function EChart({ option, className, onClick }: {
  option: EChartsOption; className?: string;
  onClick?: (params: {
    name?: string; value?: unknown; dataType?: string;
    data?: Record<string, unknown>; treePathInfo?: { name: string }[];
  }) => void;
}) {
```

```ts
    chart.on("click", (params) => onClickRef.current?.(params as {
      name?: string; value?: unknown; dataType?: string;
      data?: Record<string, unknown>; treePathInfo?: { name: string }[];
    }));
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/EChart.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/EChart.tsx shell/src/builder/EChart.test.tsx
git commit -m "feat(shell): register SunburstChart, widen EChart click params (SP-14f)"
```

---

### Task 11: Shell — `chart.tsx`: new chart types in the builder UI, generalized click handling

**Files:**
- Modify: `shell/src/builder/widgets/chart.tsx:15-19` (`CHART_TYPES`), `:35-40` (`defaultProps`), `:43-123` (`PropsPanel`), `:198-205` (`handleClick`)
- Test: `shell/src/builder/widgets/chart.test.tsx`

**Interfaces:**
- Consumes: `resolveClickFilter`, `ClickParams` from `chartOption.ts` (Task 9).
- Produces: 5 new `CHART_TYPES` entries; `PropsPanel` shows `encodings` text inputs for sankey (source/target) and treemap/sunburst (1-3 levels, add/remove), a "Nombre de classes" input for histogram, and hides the plain `categoryField`/`valueField` inputs for sankey/treemap/sunburst (funnel and histogram keep them). `handleClick` delegates to `resolveClickFilter` instead of hardcoding `categoryField`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chart.test.tsx`:

```tsx
test("PropsPanel offers the 5 new chart types", () => {
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={vi.fn()} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const select = screen.getByLabelText("Type de graphique") as HTMLSelectElement;
  const values = Array.from(select.options).map((o) => o.value);
  expect(values).toEqual(expect.arrayContaining(["sankey", "treemap", "sunburst", "funnel", "histogram"]));
});

test("PropsPanel shows source/target encodings for sankey, hides categoryField/valueField", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "sankey" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Champ source")).toBeInTheDocument();
  expect(screen.getByLabelText("Champ cible")).toBeInTheDocument();
  expect(screen.queryByLabelText("Champ catégorie")).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Champ source"), "o");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { source: "o" } }));
});

test("PropsPanel lets the author add up to 3 hierarchy levels for treemap/sunburst", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "treemap", encodings: { levels: ["region"] } }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Niveau 1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "+ Niveau" }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { levels: ["region", ""] } }));
});

test("PropsPanel shows a bin-count field for histogram", () => {
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "histogram" }} dataSources={[]} onChange={vi.fn()} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Nombre de classes")).toBeInTheDocument();
});

test("handleClick uses resolveClickFilter — treemap click cross-filters on the deepest level", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  const treeRecords = state({ records: [{ id: "1", properties: { region: "Nord", value: 1 } }], datasetId: "ds-1" });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart props={{ chartType: "treemap", encodings: { levels: ["region"] }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: treeRecords } as WidgetContext} />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  // The shared EChart mock (top of file) fires onClick({ name: "Nord" }) — no
  // treePathInfo, so resolveClickFilter falls back to depth 0 → levels[0].
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx -t "new chart types|sankey|hierarchy levels|bin-count|deepest level"`
Expected: FAIL

- [ ] **Step 3: Implement — `CHART_TYPES`, `defaultProps`, imports**

In `shell/src/builder/widgets/chart.tsx`, replace the import of `buildOption`/`buildCompareOption` (line 9) to also pull in the new pieces:

```ts
import { buildOption, buildCompareOption, resolveClickFilter, type ChartProps, type ClickParams, type ComparePoint } from "./chartOption";
```

Replace `CHART_TYPES` (lines 15-19):

```ts
const CHART_TYPES: [string, string][] = [
  ["bar", "Barres"], ["line", "Lignes"], ["area", "Aires"], ["scatter", "Nuage de points"],
  ["pie", "Camembert"], ["doughnut", "Anneau"], ["radar", "Radar"], ["heatmap", "Carte de chaleur"],
  ["gauge", "Jauge"], ["boxplot", "Boîte à moustaches"],
  ["sankey", "Flux (sankey)"], ["treemap", "Zones hiérarchiques (treemap)"],
  ["sunburst", "Soleil hiérarchique (sunburst)"], ["funnel", "Entonnoir"], ["histogram", "Histogramme"],
];
```

Add `bins: 10` to `defaultProps` (line 39, right after `compareEnabled: false, comparePeriod: "previous",`):

```ts
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous", bins: 10,
```

- [ ] **Step 4: Implement — `PropsPanel`**

Replace the `PropsPanel` body (lines 43-123). The shape is the same as today plus 3 new conditional blocks; the existing category/value fields are now gated by `showCategoryValue`:

```tsx
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      const chartType = String(props.chartType ?? "bar");
      const showCompare = chartType === "line" || chartType === "area";
      const showCategoryValue = chartType !== "sankey" && chartType !== "treemap" && chartType !== "sunburst";
      const showSankeyEncodings = chartType === "sankey";
      const showHierarchyEncodings = chartType === "treemap" || chartType === "sunburst";
      const showBins = chartType === "histogram";
      const encodings = (props.encodings as ChartProps["encodings"]) ?? {};
      const setEncodings = (patch: Record<string, unknown>) => set({ encodings: { ...encodings, ...patch } });
      const levels = encodings.levels ?? [];
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })} />
          <label className={labelCls}>Type de graphique
            <select aria-label="Type de graphique" className={inputCls}
              value={chartType} onChange={(e) => set({ chartType: e.target.value })}>
              {CHART_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          {showCategoryValue && (
            <>
              <label className={labelCls}>Champ catégorie / X
                <input aria-label="Champ catégorie" className={inputCls}
                  value={String(props.categoryField ?? "")} onChange={(e) => set({ categoryField: e.target.value })} />
              </label>
              <label className={labelCls}>Champ valeur (camembert / jauge / comparaison)
                <input aria-label="Champ valeur" className={inputCls}
                  value={String(props.valueField ?? "")} onChange={(e) => set({ valueField: e.target.value })} />
              </label>
            </>
          )}
          {showSankeyEncodings && (
            <>
              <label className={labelCls}>Champ source
                <input aria-label="Champ source" className={inputCls}
                  value={String(encodings.source ?? "")} onChange={(e) => setEncodings({ source: e.target.value })} />
              </label>
              <label className={labelCls}>Champ cible
                <input aria-label="Champ cible" className={inputCls}
                  value={String(encodings.target ?? "")} onChange={(e) => setEncodings({ target: e.target.value })} />
              </label>
            </>
          )}
          {showHierarchyEncodings && (
            <div className={labelCls}>
              <span>Niveaux (hiérarchie)</span>
              {levels.map((lvl, i) => (
                <div key={i} className="flex items-center gap-1">
                  <input aria-label={`Niveau ${i + 1}`} className={inputCls}
                    value={lvl} onChange={(e) => setEncodings({ levels: levels.map((l, j) => (j === i ? e.target.value : l)) })} />
                  <button type="button" aria-label={`Retirer le niveau ${i + 1}`} className="text-xs text-red-600"
                    onClick={() => setEncodings({ levels: levels.filter((_, j) => j !== i) })}>✕</button>
                </div>
              ))}
              {levels.length < 3 && (
                <button type="button" className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                  onClick={() => setEncodings({ levels: [...levels, ""] })}>
                  + Niveau
                </button>
              )}
            </div>
          )}
          {showBins && (
            <label className={labelCls}>Nombre de classes
              <input aria-label="Nombre de classes" type="number" min={1} max={100} className={inputCls}
                value={String(props.bins ?? 10)} onChange={(e) => set({ bins: Number(e.target.value) })} />
            </label>
          )}
          {showCompare && (
            <>
              <label className="flex items-center gap-2">
                <input type="checkbox" aria-label="Comparer les périodes"
                  checked={Boolean(props.compareEnabled)} onChange={(e) => set({ compareEnabled: e.target.checked })} />
                Comparer les périodes
              </label>
              <label className={labelCls}>Période de référence
                <select aria-label="Période de référence" className={inputCls}
                  value={String(props.comparePeriod ?? "previous")} onChange={(e) => set({ comparePeriod: e.target.value })}>
                  <option value="previous">Période précédente</option>
                  <option value="sameLastYear">Même période l'an dernier</option>
                </select>
              </label>
            </>
          )}
          <label className={labelCls}>Type d'axe X
            <select aria-label="Type d'axe X" className={inputCls}
              value={String(props.xAxisType ?? "category")} onChange={(e) => set({ xAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Type d'axe Y
            <select aria-label="Type d'axe Y" className={inputCls}
              value={String(props.yAxisType ?? "value")} onChange={(e) => set({ yAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Unité de l'axe Y
            <input aria-label="Unité de l'axe Y" className={inputCls}
              value={String(props.yAxisUnit ?? "")} onChange={(e) => set({ yAxisUnit: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du graphique" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Empiler les séries"
              checked={Boolean(props.stack)} onChange={(e) => set({ stack: e.target.checked })} />
            Empiler les séries
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Afficher la légende"
              checked={props.legend !== false} onChange={(e) => set({ legend: e.target.checked })} />
            Afficher la légende
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Activer le zoom"
              checked={Boolean(props.zoom)} onChange={(e) => set({ zoom: e.target.checked })} />
            Activer le zoom
          </label>
          <label className={labelCls}>Option ECharts avancée (JSON)
            <textarea aria-label="Option ECharts avancée (JSON)"
              className="rounded-md border border-slate-300 p-2 font-mono text-xs" rows={4}
              placeholder='{"color":["#f00"]}'
              value={String(props.advancedOption ?? "")} onChange={(e) => set({ advancedOption: e.target.value })} />
          </label>
        </div>
      );
    },
```

- [ ] **Step 5: Implement — `handleClick`**

Replace lines 198-205 (inside `Component`, the default-mode render path):

```tsx
      const option = buildOption(props as unknown as ChartProps, data.records);
      function handleClick(params: ClickParams) {
        const resolved = resolveClickFilter(chartType, props as unknown as ChartProps, params);
        if (!resolved) return;
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [resolved.field]: resolved.value });
        if (data?.datasetId) setCrossFilter(data.datasetId, resolved.field, resolved.value, originSourceId);
      }
```

(This removes the now-unused `const categoryField = String(props.categoryField ?? "");` line — delete it.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx`
Expected: PASS — new tests plus the full existing file (bar-click-cross-filter, compare-periods, explorer menu, etc.) green, since `resolveClickFilter("bar", {categoryField}, {name})` reproduces the old hardcoded logic exactly.

- [ ] **Step 7: Run the full shell unit suite and typecheck for non-regression**

Run: `cd shell && npm run test && npm run build`
Expected: PASS — `tsc --noEmit` clean (in particular: `EChart`'s widened `onClick` type is a superset, so `chart.tsx`'s `handleClick: (params: ClickParams) => void` still satisfies it), `vite build` clean, full Vitest suite green.

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx
git commit -m "feat(shell): chart widget exposes sankey/treemap/sunburst/funnel/histogram with generalized cross-filter click (SP-14f)"
```

---

### Task 12: E2E — new chart types in `analytics-context.spec.ts`

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts` (append new scenarios, reuse `createApp`/`addFeaturesSource`/`promoteLastSource` helpers already at the top of the file)

**Interfaces:**
- Consumes: `createApp`, `addFeaturesSource`, `promoteLastSource`, `mockCore` — all already defined in the file (see lines 26-45 and the `mocks.ts` import).

**Design note carried into this task:** ECharts renders to `<canvas>`, so existing E2E click tests work by clicking a *computed pixel position* on the canvas, which is only reliable when the layout is simple and predictable (e.g. 2 equal-width bars). Treemap/sunburst/sankey use layout algorithms (squarified rectangles, Sankey flow routing) whose pixel positions aren't predictable from source data the way a bar chart's are — pinning a blind-coordinate click to a specific node would be flaky. Given `resolveClickFilter`'s click-resolution logic is already fully covered by precise, non-flaky unit tests (Task 9) and the funnel/histogram cases behave exactly like the existing bar/pie click test, this task's E2E scope is: (1) a real click-driven cross-filter scenario for **funnel** (predictable layout, same technique as the existing bar test), (2) a render-only smoke test for **sankey**, **treemap**, **sunburst** (proves the full stack — builder UI → `/aggregate` with multi-field `groupBy` → `EChart` — works end-to-end without crashing), (3) a render + no-cross-filter-on-click scenario for **histogram**, and (4) the mandatory non-regression pass.

- [ ] **Step 1: Write the funnel click-cross-filter scenario**

Append to `shell/e2e/analytics-context.spec.ts` (mirrors the existing "a chart click cross-filters a table" scenario at line 51, swapping `chartType` to `funnel` and reusing the same `analytics` collection/mock):

```ts
test("a funnel click cross-filters a table on the same dataset (SP-14f)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }, { name: "valeur", type: "number" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    const cat = new URL(route.request().url()).searchParams.get("categorie");
    const all = [
      { id: 1, properties: { categorie: "Nord", valeur: 100 } },
      { id: 2, properties: { categorie: "Sud", valeur: 100 } },
    ];
    const features = cat ? all.filter((f) => f.properties.categorie === cat) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Funnel cross-filter");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("funnel");
  await page.getByLabel("Champ catégorie").fill("categorie");
  await page.getByLabel("Champ valeur (camembert / jauge / comparaison)").fill("valeur");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  // Funnel with 2 equal-value stages stacks them top/bottom — top half is "Nord" (first stage).
  const topStage = { x: box.width * 0.5, y: box.height * 0.25 };
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: topStage });
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
});
```

- [ ] **Step 2: Write the sankey/treemap/sunburst render smoke test**

```ts
test("sankey, treemap and sunburst render from a multi-field groupBy dataset (SP-14f)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/flows/schema", async (route) => {
    await route.fulfill({
      json: { collection: "flows", pk: "id", geometry: null,
        fields: [{ name: "origin", type: "string" }, { name: "destination", type: "string" }, { name: "amount", type: "number" }] },
    });
  });
  await page.route("**/collections/flows/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: ["origin", "destination"],
        rows: [
          { origin: "Paris", destination: "Lyon", value: 10 },
          { origin: "Paris", destination: "Marseille", value: 5 },
        ],
      },
    });
  });

  await createApp(page, "Sankey/Treemap/Sunburst smoke");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Type de la source/).last().selectOption("statistics");
  await page.getByLabel(/Collection de la source/).last().fill("flows");
  await page.getByLabel(/Grouper par/).last().fill("origin,destination");
  await page.getByLabel(/Champ agrégé/).last().fill("amount");

  for (const [type, label] of [["sankey", "Flux (sankey)"], ["treemap", "Zones hiérarchiques (treemap)"], ["sunburst", "Soleil hiérarchique (sunburst)"]] as const) {
    await page.getByRole("button", { name: "Graphique" }).click();
    await page.getByLabel("Source de données").selectOption({ index: 1 });
    await page.getByLabel("Type de graphique").selectOption(type);
    if (type === "sankey") {
      await page.getByLabel("Champ source").fill("origin");
      await page.getByLabel("Champ cible").fill("destination");
    } else {
      await page.getByLabel("Niveau 1").fill("origin");
    }
    void label;
  }
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByTestId("echart").locator("canvas")).toHaveCount(3);
});
```

- [ ] **Step 3: Write the histogram render + no-click-filter scenario**

```ts
test("a histogram renders binned data and never cross-filters on click (SP-14f)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/pops/schema", async (route) => {
    await route.fulfill({
      json: { collection: "pops", pk: "id", geometry: null, fields: [{ name: "pop", type: "number" }] },
    });
  });
  await page.route("**/collections/pops/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "bucketIndex", rows: [
        { bucketIndex: 0, bucketStart: 0, bucketEnd: 5, count: 3 },
        { bucketIndex: 1, bucketStart: 5, bucketEnd: 10, count: 7 },
      ] },
    });
  });

  await createApp(page, "Histogram smoke");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Type de la source/).last().selectOption("statistics");
  await page.getByLabel(/Collection de la source/).last().fill("pops");
  await page.getByLabel(/Champ agrégé/).last().fill("pop");
  await page.getByLabel(/Nombre de classes/).last().fill("2");

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("histogram");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  let sawItemsRequest = false;
  page.on("request", (r) => { if (r.url().includes("/collections/pops/items")) sawItemsRequest = true; });
  await chart.click({ position: { x: box.width * 0.5, y: box.height * 0.5 } });
  await page.waitForTimeout(300); // no debounce/refetch to await — just proving nothing fires
  expect(sawItemsRequest).toBe(false);
});
```

- [ ] **Step 4: Run the new scenarios**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/analytics-context.spec.ts -g "SP-14f"`
Expected: PASS (4 new scenarios)

- [ ] **Step 5: Run the full E2E suite for non-regression**

Run: `cd shell && npm run e2e`
Expected: PASS — all 18+ specs, including the full `analytics-context.spec.ts`, stay green.

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover funnel cross-filter, sankey/treemap/sunburst/histogram rendering (SP-14f)"
```

---

## Final verification

- [ ] Run the complete cross-stack suite one more time before declaring the branch done:

```bash
cd core && uv run pytest
cd ../shell && npm run test && npm run build && npm run e2e
```

Expected: all green — core suite (606+ pre-existing + ~20 new from Tasks 1-3), full shell Vitest suite (62+ files including the new/modified `chartOption.test.ts`, `chart.test.tsx`, `DataSourcePanel.test.tsx`, `itemClient.test.ts`, `EChart.test.tsx`), `tsc --noEmit` + `vite build` clean, 18+ E2E specs (4 new SP-14f scenarios in `analytics-context.spec.ts`).
