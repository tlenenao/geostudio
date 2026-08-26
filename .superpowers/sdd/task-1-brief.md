## Task 1: Core — `sample` capability on the aggregate route

**Files:**
- Modify: `core/app/analytics/aggregate.py`
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `AggregateRequestBody.sample: int | None`; `run_collection_aggregate(...)` returns `("value", [{"value": <float>}, ...])` when `request.sample` is set — a shape distinct from the groupBy path's `(categoryKey, rows)`, but the exact same return type (`tuple[str | list[str], list[dict[str, Any]]]`), so no caller-side type change is needed.

- [ ] **Step 1: Write the failing unit tests**

Append to `core/tests/test_analytics_aggregate.py` (same file, same fixtures
`conn`/`TABLE_INFO`/`_write_partition`/`_row` already defined at the top):

```python
def test_sample_returns_bounded_values_for_the_field(tmp_path, conn):
    _write_partition(
        tmp_path,
        rows=[_row(i, "Nord", "2025", i, lsn=1) for i in range(1, 21)],
    )
    request = AggregateRequestBody(field="pop", sample=5)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert len(rows) == 5
    values = {r["value"] for r in rows}
    assert values.issubset(set(range(1, 21)))


def test_sample_excludes_non_castable_values(tmp_path, conn):
    rows = [_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)]
    # pop is declared "integer" in TABLE_INFO but DuckDB will TRY_CAST a
    # non-numeric string to NULL rather than raise — simulate that with a
    # tombstoned row instead, since _row's pop is always an int: exercise
    # the WHERE value IS NOT NULL clause via a collection with fewer than
    # `sample` rows instead (the boundary that actually matters here).
    _write_partition(tmp_path, rows=rows)
    request = AggregateRequestBody(field="pop", sample=100)

    _category_key, result_rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    # Sampling more rows than exist returns everything, not an error.
    assert {r["value"] for r in result_rows} == {10, 20}


def test_sample_without_field_raises(tmp_path, conn):
    request = AggregateRequestBody(sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_groupby_raises(tmp_path, conn):
    request = AggregateRequestBody(groupBy="region", field="pop", sample=10)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_with_bins_raises(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10, bins=5)
    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="villes",
            table_info=TABLE_INFO,
            request=request,
        )
    assert exc.value.field == "sample"


def test_sample_out_of_bounds_raises(tmp_path, conn):
    for bad in (0, 2001):
        request = AggregateRequestBody(field="pop", sample=bad)
        with pytest.raises(UnknownAggregateField) as exc:
            run_collection_aggregate(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="villes",
                table_info=TABLE_INFO,
                request=request,
            )
        assert exc.value.field == "sample"


def test_sample_on_empty_collection_returns_no_rows(tmp_path, conn):
    request = AggregateRequestBody(field="pop", sample=10)

    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=request,
    )

    assert category_key == "value"
    assert rows == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k sample -v`
Expected: FAIL — `AggregateRequestBody` has no field `sample` (Pydantic
`ValidationError: Extra inputs are not permitted` or similar).

- [ ] **Step 3: Add the `sample` field and its validation**

In `core/app/analytics/aggregate.py`, add to `AggregateRequestBody` (next to
`bins: int | None = None`):

```python
class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    p: float | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    geomIntersects: dict[str, Any] | None = None
    bucket: Literal["hour", "day", "week", "month", "quarter", "year"] | None = None
    bins: int | None = None
    sample: int | None = None
```

In `_validate_fields`, right after the existing `if request.bins is not None:`
block:

```python
    if request.sample is not None:
        if request.field is None:
            raise UnknownAggregateField("sample", "sample requires a field")
        if fields:
            raise UnknownAggregateField("sample", "sample cannot combine with groupBy")
        if request.bins is not None:
            raise UnknownAggregateField("sample", "sample cannot combine with bins")
        if not (1 <= request.sample <= 2000):
            raise UnknownAggregateField("sample", "sample must be between 1 and 2000")
```

- [ ] **Step 4: Add the DuckDB sampling routine**

In `core/app/analytics/aggregate.py`, add a new function right after
`_run_binned_histogram` (same file, same section):

```python
def _run_sample(
    conn: duckdb.DuckDBPyConnection,
    *,
    dedup_cte: str,
    where_sql: str,
    where_params: list[Any],
    field: str,
    sample: int,
) -> list[dict[str, Any]]:
    field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    not_null_clause = f"{field_expr} IS NOT NULL"
    full_where = f"{where_sql} AND {not_null_clause}" if where_sql else f"WHERE {not_null_clause}"
    sql = (
        f"{dedup_cte} SELECT {field_expr} AS value FROM live {full_where} "
        f"USING SAMPLE {int(sample)} ROWS"
    )
    return _fetch_rows(conn, sql, where_params)
```

Wire it into `run_collection_aggregate`, right after the existing
`if request.bins is not None:` block returns:

```python
    if request.sample is not None:
        assert request.field is not None
        rows = _run_sample(
            conn,
            dedup_cte=dedup_cte,
            where_sql=where_sql,
            where_params=where_params,
            field=request.field,
            sample=request.sample,
        )
        return "value", rows
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k sample -v`
Expected: PASS (7 tests). **If `USING SAMPLE ... ROWS` raises a DuckDB
syntax error**, this is exactly the kind of thing this repo's own history
(SP-11b's bbox spike) says to verify empirically rather than trust from
memory — try `USING SAMPLE reservoir({n} ROWS)` as the fallback spelling
and re-run; keep whichever the real DuckDB version installed here accepts.

- [ ] **Step 6: Add one route-level test**

In `core/tests/test_features_aggregate_routes.py`, following the existing
pattern (`_register_collection` helper, `client` fixture already in that
file) — add:

```python
def test_aggregate_sample_returns_bare_values(env):
    client, session = env
    col = _register_collection(client, public=True)
    client.post(
        f"/collections/{col['id']}/items",
        json={
            "type": "Feature",
            "properties": {"region": "Nord", "annee": "2025", "pop": 42},
            "geometry": None,
        },
    )

    response = client.post(f"/collections/{col['id']}/aggregate", json={"field": "pop", "sample": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["categoryKey"] == "value"
    assert body["rows"] == [{"value": 42.0}]
```

Read the actual feature-creation payload shape used by neighboring tests in
that file first (grep `client.post(f"/collections/{col\['id'\]}/items"` in
the same file) and match it exactly — do not guess the property/geometry
shape.

- [ ] **Step 7: Run the full core suite**

Run: `cd core && uv run pytest -v`
Expected: PASS, count ≥ 1868 + 8 new tests, 0 failed.

- [ ] **Step 8: Lint gates**

Run: `cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py core/tests/test_features_aggregate_routes.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute la capacité sample à l'agrégat de collection

Nécessaire au calcul des seuils naturels (Jenks) côté shell (SP-25) :
un échantillon borné de valeurs, sans groupBy ni géométrie.
EOF
)"
```

---

