### Task 1: Core — `bucket` param on `/collections/{id}/aggregate`

**Files:**
- Modify: `core/app/analytics/aggregate.py:24-31` (`AggregateRequestBody`), `core/app/analytics/aggregate.py:68-84` (`_validate_fields`), `core/app/analytics/aggregate.py:197-223` (`run_collection_aggregate`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `AggregateRequestBody.bucket: Literal["day", "week", "month"] | None = None`. When set, `run_collection_aggregate` groups by `DATE_TRUNC(bucket, TRY_CAST(groupBy AS TIMESTAMP))` instead of the raw `groupBy` column, using the same `category_key = request.groupBy` and the same `_pivot_measures`/`_pivot_split` shape as before. `bucket` without `groupBy` raises `UnknownAggregateField("bucket", ...)`.

- [ ] **Step 1: Write the failing core tests**

Append to `core/tests/test_analytics_aggregate.py` (uses the existing `TABLE_INFO`, `_write_partition`, `_row`, `conn` fixture already in the file — `_row`'s third positional arg is stored under the `annee` column, which we reuse to hold date-like strings for these tests since `TABLE_INFO` already declares it as a plain string column):

```python
def test_bucket_groups_rows_by_day(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
        _row(3, "Nord", "2026-01-06", 4, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="count")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "annee"
    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 00:00:00", "value": 2},
        {"annee": "2026-01-06 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_month(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Nord", "2026-01-20", 5, lsn=1),
        _row(3, "Nord", "2026-02-10", 7, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="month", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-01 00:00:00", "value": 15},
        {"annee": "2026-02-01 00:00:00", "value": 7},
    ]


def test_bucket_without_group_by_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2026-01-05", 10, lsn=1)])
    request = AggregateRequestBody(bucket="day")

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bucket"


def test_bucket_on_non_castable_field_groups_under_a_null_bucket(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "pas-une-date", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    by_key = {r["annee"]: r["value"] for r in rows}
    assert by_key["None"] == 10
    assert by_key["2026-01-05 00:00:00"] == 3
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bucket -v`
Expected: FAIL — `AggregateRequestBody` has no field `"bucket"` (pydantic `ValidationError` / `TypeError`).

- [ ] **Step 3: Implement `bucket` in `core/app/analytics/aggregate.py`**

Add the import and the new field (`core/app/analytics/aggregate.py:1-31`):

```python
from typing import Literal

from pydantic import BaseModel


class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None


class AggregateRequestBody(BaseModel):
    groupBy: str | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    bucket: Literal["day", "week", "month"] | None = None
```

Add the guard at the top of `_validate_fields` (`core/app/analytics/aggregate.py:68-84`):

```python
def _validate_fields(request: AggregateRequestBody, table_info) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    if request.bucket is not None and not request.groupBy:
        raise UnknownAggregateField("bucket", "bucket requires groupBy")

    check(request.groupBy, "groupBy")
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

Switch `cat_expr` in `run_collection_aggregate` (`core/app/analytics/aggregate.py:197-208`, only the `cat_expr` line changes):

```python
def run_collection_aggregate(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info, request: AggregateRequestBody,
) -> tuple[str, list[dict]]:
    category_key = request.groupBy or "group"
    _validate_fields(request, table_info)

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)
    if request.bucket:
        cat_expr = f"DATE_TRUNC({_sql_lit(request.bucket)}, TRY_CAST({_qi(request.groupBy)} AS TIMESTAMP))"
    else:
        cat_expr = _qi(request.groupBy) if request.groupBy else "'Total'"
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bucket -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full core test suite for non-regression**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py tests/test_features_aggregate_routes.py -v`
Expected: PASS — all pre-existing tests unaffected (`bucket` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): add optional bucket param to /collections/{id}/aggregate"
```

---

