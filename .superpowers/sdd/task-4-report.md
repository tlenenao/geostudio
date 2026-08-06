# Task 4 report — Structural graph validation + CORE_ETL_ENABLED guard (SP-15a)

Note: this file previously held a stale report from a different plan's task 4
(SP-14n shell types). Overwritten with this task's report (SP-15a plan,
"Pipeline: socle headless", task 4 of 11).

## Commit

- `a44c3b8` — `feat(core): validate pipeline graph structure at save time, gate on CORE_ETL_ENABLED`
  - `core/app/configs/pipeline_validation.py` (new)
  - `core/app/configs/routes.py` (modified: import, `_require_etl_enabled_for_pipeline` helper, three call-site insertions in `create_config`, `update_config`, `update_config_by_item`)
  - `core/tests/test_pipeline_config_validation.py` (new)

Staged only these three files exactly per the brief's Step 7 (confirmed via
`git status` before commit — unrelated pre-existing dirty files under
`.superpowers/sdd/` and untracked `docs/superpowers/...` files were left
untouched).

## TDD steps followed

1. Wrote `core/tests/test_pipeline_config_validation.py` verbatim from the brief.
2. Ran `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
   → FAILED as expected: collection error,
   `ImportError: cannot import name 'pipeline_validation' from 'app.configs'`
   (same root cause as the brief's expected `ModuleNotFoundError`).
3. Before implementing, read the real current `core/app/configs/routes.py`,
   `dataset_validation.py`, `bookmark_validation.py`, and `schemas.py` to
   confirm the brief's assumed structure matched reality. It matched exactly
   — no adaptation needed (`is_etl_enabled()` already existed in
   `app/auth/dependency.py` from Task 1; `PipelineNode`/`PipelineEdge`/
   `PipelinePayload` already existed in `schemas.py` from Task 2).
4. Implemented `core/app/configs/pipeline_validation.py` verbatim from the
   brief: `_node_validators` registry dict, `register_pipeline_node_validator`,
   `_check_linear_topology` (incoming-edge count per node), `_check_acyclic`
   (DFS 3-color white/gray/black cycle detection), `validate_pipeline_payload`
   (acyclic check first, then linear-topology check, then per-node validator
   dispatch raising 422 on unknown op).
5. Wired `core/app/configs/routes.py`: added `is_etl_enabled` to the existing
   auth import, added the `_validate_pipeline_payload` import right after the
   dataset one, added `_require_etl_enabled_for_pipeline` right after
   `_validate_extension_scope`, and inserted the guard + validator calls at
   all three write points (`create_config`, `update_config`,
   `update_config_by_item`) — guard placed FIRST in each sequence per the
   brief's explicit final-ordering instruction (cheapest check, fail fast),
   overriding an earlier draft ordering shown in the brief's own prose.
6. Ran `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
   → PASSED, 5/5:
   - `test_valid_linear_pipeline_saves`
   - `test_disabled_capability_refuses_pipeline_creation`
   - `test_disabled_capability_does_not_affect_other_kinds`
   - `test_cyclic_graph_rejected`
   - `test_node_with_two_incoming_edges_rejected`
7. Regression check, exact brief command:
   `cd core && uv run pytest tests/test_configs_extension_permissions.py tests/test_create_dataset.py tests/test_read_only_mode.py -v`
   → PASSED, 22/22, unchanged.
8. Extra safety net beyond the brief's ask, run anyway before committing:
   `cd core && uv run pytest -q` (full core suite)
   → 919 passed, 114 skipped (postgis-marked, require docker — pre-existing/expected).
9. Committed exactly the three named files with the exact message given in
   the brief.

## Concerns

None. The brief's assumed code (routes.py structure/import ordering,
dataset_validation.py's registry pattern, schemas.py's pipeline models,
`is_etl_enabled()`) all matched the real repository state exactly, so the
brief's code was used verbatim as instructed with no deviation.

One thing worth flagging for whoever does Task 5: `validate_pipeline_payload`
raises `HTTPException(422, "unknown op '<op>'")` for any node whose `op` has
no registered validator. Right now (before Task 5 registers the real op
validators) that means *any* pipeline node using a real op other than the two
faked in this task's test fixture will 422 in production — this is expected
and intentional per the brief (Task 5 registers `reader.collection`,
`writer.collection`, `transform.filter`, etc. via
`register_pipeline_node_validator`, imported for side effect by `app.main`).
Not a defect, just noting the current window where pipeline configs cannot
actually be saved end-to-end until Task 5 lands.

## Status: DONE
