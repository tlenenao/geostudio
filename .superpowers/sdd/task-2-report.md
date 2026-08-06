# Task 2 report — `BuilderConfig` gains `kind="pipeline"` (SP-15a)

## Commit

- `b68e069` — `feat(core): add BuilderConfig kind=pipeline (PipelinePayload/Node/Edge)`
  - Files: `core/app/configs/schemas.py`, `core/tests/test_pipeline_config_schema.py`
  - Exactly the two files named in the brief's Step 6; other unrelated
    working-tree changes present before this task started (`.superpowers/sdd/*`,
    two SP-14n/SP-15a docs) were left untouched/unstaged.

## Steps followed (brief §Task 2)

1. **Read the real file first** (`core/app/configs/schemas.py`) to confirm the
   brief's assumed structure (import line, `DatasetPayload`/`BookmarkPayload`
   layout, `BuilderConfig.kind`/`_require_kind_payload`) matched exactly —
   it did, no adaptation needed.
2. **Wrote the failing tests** — created `core/tests/test_pipeline_config_schema.py`
   verbatim from the brief (7 tests).
3. **Confirmed the expected failure**:
   `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
   → 6 failed / 1 passed. All 6 failures were the expected
   `kind: Input should be 'app', 'dashboard', 'map', 'site', 'dataset' or 'bookmark'`
   literal_error — failing because `"pipeline"` wasn't yet a valid `kind`, not
   for any other reason. `test_pipeline_config_sans_payload_rejete` happened
   to pass even at RED since any invalid `kind` already raises `ValidationError`.
4. **Implemented the schema** in `core/app/configs/schemas.py`, following the
   existing `DatasetPayload`/`BookmarkPayload` precedent:
   - Added `Any` to the top `typing` import.
   - Added `PipelineNode`, `PipelineEdge` (aliased `from_`/`from`, same idiom
     as `Message`/`BookmarkTimeRange`), `PipelinePayload` with a
     `model_validator(mode="after")` graph check (unique node ids, edges
     reference known node ids, at least one `reader` node, at least one
     `writer` node) — inserted right after `BookmarkPayload`, before
     `BuilderConfig`.
   - Extended `BuilderConfig.kind` literal with `"pipeline"`.
   - Added `pipeline: PipelinePayload | None = None` field right after
     `bookmark: BookmarkPayload | None = None`.
   - Added the `pipeline`/`self.pipeline is None` branch to
     `_require_kind_payload`, right after the bookmark check.
   All inserted verbatim per the brief's Step 3 code blocks — no deviations.
5. **Ran the new tests to green**:
   `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
   → **7 passed** in 0.09s.
6. **Regression check**:
   `cd core && uv run pytest tests/test_dataset_config_schema.py tests/test_configs_models.py -v`
   → **16 passed** in 0.19s (14 dataset-schema tests + 2 config-model tests),
   no change in outcome vs. before this task.
7. **Committed** exactly the two files named in the brief.

## Concerns

None. The brief's code matched the real file's structure exactly — no
adaptation was needed beyond straight insertion. No existing `Any` import
collision, no naming collisions with `PipelineNode`/`PipelineEdge`/
`PipelinePayload`. All later-task interfaces the brief promises
(`config.pipeline`, `node.id`/`node.kind`/`node.op`/`node.params`,
`edge.from_`/`edge.to`) are present and exercised by the tests.
