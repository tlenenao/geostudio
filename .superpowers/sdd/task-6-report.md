# Task 6 report — Bounded SQL expression validation + DAG compiler (SP-15a)

## Commit

- `4b45ec0` — `feat(core): bounded SQL expression validation + linear+join DAG compiler`
  (4 files: `core/app/pipelines/expr_validation.py`, `core/app/pipelines/compiler.py`,
  `core/tests/test_pipeline_expr_validation.py`, `core/tests/test_pipeline_compiler.py`)

## Signature verification (before writing code)

Read `core/app/analytics/sql_sandbox.py` first, as instructed, before trusting
the brief. All four consumed names matched the brief exactly, no adjustment
needed:
- `parse_ast(conn: duckdb.DuckDBPyConnection, sql: str) -> dict`
- `validate_select_only(ast: dict) -> None`
- `collect_table_refs(ast: dict) -> set[str]`
- `SqlSandboxError(Exception)`

Also checked `app.configs.schemas.PipelineNode`/`PipelineEdge` (fields `id`,
`kind`, `op`, `params`, `x`/`y`, `title`; `PipelineEdge.from_` aliased to
`"from"`, `populate_by_name=True`) and the six `Transform*Params` classes in
`app/pipelines/ops/schemas.py` — both matched the brief's assumptions
verbatim, no signature drift found.

## TDD steps and test commands run

1. `core/tests/test_pipeline_expr_validation.py` written verbatim from brief.
   - `cd core && uv run pytest tests/test_pipeline_expr_validation.py -v`
     → FAIL as expected: `ModuleNotFoundError: No module named 'app.pipelines.expr_validation'`.
   - Implemented `core/app/pipelines/expr_validation.py` verbatim from brief.
   - Re-ran same command → **5 passed**.
2. `core/tests/test_pipeline_compiler.py` written verbatim from brief.
   - `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
     → FAIL as expected: `ModuleNotFoundError: No module named 'app.pipelines.compiler'`.
   - Implemented `core/app/pipelines/compiler.py` verbatim from brief.
   - Re-ran same command → **12 passed** (brief's step 8 comment says "11
     tests green" — an off-by-one in the brief's narration; the test file it
     specifies verbatim actually contains 12 test functions and all 12 pass.
     Not a code defect, just a stale count in the brief text — noted, not
     acted on since the brief's code block is authoritative and matched).
3. Full suite: `cd core && uv run pytest -q` → **941 passed, 114 skipped**
   (no regressions elsewhere).
4. Import-boundary lint: `cd core && uv run lint-imports` → **1 kept, 0
   broken** (layered architecture contract intact — the two new modules sit
   under `app.pipelines`, consuming `app.analytics.sql_sandbox`,
   `app.configs.schemas`, `app.pipelines.ops.schemas`, all within the
   allowed layering).
5. No `ruff`/`black`/`mypy` configured in `core/pyproject.toml` beyond
   `import-linter`, so no additional lint step applied.

## Commit hygiene note

`git status` before staging showed several pre-existing modified/untracked
files under `.superpowers/sdd/*` and `docs/superpowers/*` (task briefs/reports
from earlier SP-15a tasks, plus unrelated new plan/spec docs from other work).
These were left untouched; only the 4 files named in the brief's Step 9 were
`git add`ed and committed, per the known `.superpowers/sdd/` tracking gotcha
noted in prior session memory (SP-14m notes).

Also found: this report file (`task-6-report.md`) already existed on disk
before this task ran, containing a stale report from an unrelated prior plan
run (a shell `geomIntersects` task, commit `1e9f120`, SP-14n numbering). That
is expected filename reuse across different plan executions in this repo's
`.superpowers/sdd/` scratch area — this file now holds SP-15a Task 6's report
instead.

## Concerns

None functional. The only discrepancy found was the brief's stated expected
compiler test count ("11 tests green") vs. the actual 12 tests in the file it
specifies — cosmetic, does not affect correctness or the commit.
