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

