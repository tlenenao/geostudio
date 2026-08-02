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

