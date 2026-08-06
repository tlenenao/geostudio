# Task 3 Report: Pipeline Op Catalogue (8 data-only ops)

## Summary
Successfully completed Task 3 of the SP-15a plan. Created the Phase 1 pipeline op catalogue with 8 data-only operations, passing all tests.

## Files Created
- `core/app/pipelines/__init__.py` (empty module, license header only)
- `core/app/pipelines/ops/__init__.py` (empty module, license header only)
- `core/app/pipelines/ops/schemas.py` (8 Pydantic param classes + 3 exported functions)
- `core/tests/test_pipeline_ops_schemas.py` (comprehensive test suite)

## Implementation

### Op Catalogue Structure
Created `core/app/pipelines/ops/schemas.py` with:

1. **8 Pydantic param classes**:
   - `ReaderCollectionParams` — (collectionId: str)
   - `TransformFilterParams` — (expr: str)
   - `TransformSelectParams` — (columns: dict[str, str | None] with default empty)
   - `TransformDeriveParams` — (column: str, expr: str)
   - `TransformAggregateParams` — (groupBy: list, metrics: dict with defaults)
   - `TransformJoinParams` — (withCollectionId: str, on: str, how: Literal["inner", "left"] default="inner")
   - `WriterCollectionParams` — (collectionId: str)
   - `WriterExportParams` — (format: Literal["geojson", "csv"], key: str)

2. **OP_KINDS registry**: Maps op names to phase (reader/transform/writer)

3. **OP_PARAMS registry**: Maps op names to their Pydantic model class

4. **parse_op_params(op: str, params: dict) -> BaseModel**: Validates and instantiates params, raises ValueError for unknown ops

5. **ops_catalog() -> dict[str, dict]**: Exports JSON Schema for all ops, includes kind and paramsSchema

### Design Decisions
- Expressions (filter.expr, derive.expr, aggregate.metrics) are intentionally stored as strings — semantic validation happens later in `app.pipelines.expr_validation`, not here
- This module only validates the FORM of parameters, not their semantics
- JSON Schema export ready for UI consumption via GET /pipelines/ops (SP-15b)

## Testing

### Test Run
```bash
cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v
```

**Result: 15 tests PASSED**

- test_all_eight_phase1_ops_are_registered: PASSED
- test_op_kind_matches (8 parametrized): ALL PASSED
  - reader.collection → "reader"
  - transform.filter → "transform"
  - transform.select → "transform"
  - transform.derive → "transform"
  - transform.aggregate → "transform"
  - transform.join → "transform"
  - writer.collection → "writer"
  - writer.export → "writer"
- test_parse_op_params_reader_collection: PASSED
- test_parse_op_params_missing_required_field_raises: PASSED (ValidationError on missing required field)
- test_parse_op_params_unknown_op_raises: PASSED (ValueError with "unknown op" message)
- test_transform_join_defaults_how_to_inner: PASSED (default value tested)
- test_writer_export_requires_format_and_key: PASSED (both fields required)
- test_ops_catalog_exposes_json_schema_per_op: PASSED (JSON schema present for all ops)

## Commit

```
commit 3c5c0e3
feat(core): add Phase 1 pipeline op catalogue (8 data-only ops)

4 files changed, 158 insertions(+)
- core/app/pipelines/__init__.py
- core/app/pipelines/ops/__init__.py
- core/app/pipelines/ops/schemas.py
- core/tests/test_pipeline_ops_schemas.py
```

## Verification
- All code transcribed verbatim from brief — no deviations
- All tests pass on first run after implementation
- Package structure follows existing conventions
- SPDX headers correct on all Python files
- No syntax errors, no missing imports

## Status
**DONE** — Task 3 complete, ready for Task 4 (pipeline execution engine)
