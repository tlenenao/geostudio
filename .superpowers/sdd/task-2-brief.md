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

