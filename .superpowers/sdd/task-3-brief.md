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

