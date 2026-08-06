# Task 1 report — `CORE_ETL_ENABLED` capability flag

## Commit

- `33f36b7` — `feat(core): add CORE_ETL_ENABLED instance-wide capability flag`
  Files: `core/app/auth/dependency.py`, `core/app/instance/routes.py`,
  `.env.example`, `core/tests/test_read_only_mode.py`,
  `core/tests/test_etl_enabled_flag.py` (new). No unrelated files staged
  (verified with `git status` before commit — the pre-existing modifications
  to `.superpowers/sdd/progress.md` and `.superpowers/sdd/task-1-brief.md`,
  plus untracked SP-15a/SP-14n docs, were left out).

## Steps followed

1. Wrote `core/tests/test_etl_enabled_flag.py` verbatim from the brief.
2. Ran `cd core && uv run pytest tests/test_etl_enabled_flag.py -v` —
   FAILED as expected: `ImportError: cannot import name 'is_etl_enabled'
   from 'app.auth.dependency'` (1 error during collection).
3. Added `is_etl_enabled()` to `core/app/auth/dependency.py`, right after
   `is_read_only_mode()`, verbatim from the brief.
4. Replaced `core/app/instance/routes.py` verbatim from the brief
   (`GET /instance` now returns `{"readOnly": ..., "etlEnabled": ...}`).
5. Fixed the two exact-dict assertions in `core/tests/test_read_only_mode.py`
   (`test_instance_defaults_to_read_write`,
   `test_instance_reports_read_only_without_needing_auth`) to include
   `"etlEnabled": False`.
6. Added `CORE_ETL_ENABLED=false` to `.env.example` right after
   `CORE_READ_ONLY_MODE=false`.
7. Ran the combined suite:
   `cd core && uv run pytest tests/test_etl_enabled_flag.py tests/test_read_only_mode.py -v`
   → **15 passed in 3.62s** (4 from the new file, 11 from
   `test_read_only_mode.py`, all green).
8. Grepped the repo (`grep -rn '"readOnly"'`) to confirm no other consumer
   (shell TS, other core tests) asserts an exact dict on `/instance` that
   would also need updating — none found.
9. Committed exactly the five files listed in the brief's Step 8, with the
   exact commit message given.

## Concerns

None. The brief's code was followed verbatim; both target test files pass
together; no other file in the repo asserts an exact `/instance` response
shape that would have broken silently.

Note: this file previously contained a stale report from an unrelated task
(SP-14n `geomIntersects` on the DuckDB aggregate endpoint) — that content has
been replaced with this task's report.
