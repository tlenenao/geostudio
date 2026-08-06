## Task 3: `compiler.py` — SRID tracking for `transform.qgis`

**Files:**
- Modify: `core/app/pipelines/compiler.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `TransformQgisParams` (Task 2).
- Produces: `transform_output_srid("transform.qgis", ...)` now returns
  `int(outputSrid)` when set, else passes `input_srid` through unchanged.
  Consumed by Task 5 (`runtime.py`, called before the qgis dispatch branch).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_compiler.py`:

```python
def test_transform_output_srid_qgis_passes_through_by_default():
    srid = transform_output_srid(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
        input_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_qgis_uses_explicit_output_srid():
    # gdal:warpreproject's real schema (Task 1) requires DATA_TYPE/
    # MULTITHREADING/RESAMPLING too — TARGET_CRS itself is optional, but
    # included here for realism (this IS the reprojection param).
    srid = transform_output_srid(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {"TARGET_CRS": "EPSG:2154", "DATA_TYPE": 0,
                       "MULTITHREADING": False, "RESAMPLING": 0},
            "outputSrid": "EPSG:2154",
        },
        input_srid=4326,
    )
    assert srid == 2154
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k qgis -v`
Expected: FAIL — the current fallthrough (`return input_srid`) already
makes the first test pass by accident, but the second test fails (`2154 !=
4326`, `outputSrid` ignored). Confirm this asymmetry before implementing.

- [ ] **Step 3: Implement**

Modify `core/app/pipelines/compiler.py` — add `TransformQgisParams` to the
import from `app.pipelines.ops.schemas`:

```python
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformBufferParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, TransformQgisParams,
    TransformReprojectParams, TransformSelectParams,
)
```

In `transform_output_srid`, add a branch before the final `return
input_srid`:

```python
    if op == "transform.qgis":
        p = TransformQgisParams.model_validate(params)
        return int(p.outputSrid.rsplit(":", 1)[1]) if p.outputSrid is not None else input_srid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: all pass, no regression on the other transform ops' SRID tests.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/compiler.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): transform.qgis SRID tracking via explicit outputSrid"
```

---

