# Task 2 report — Core: direct validation + REST wiring (bookmark, SP-14m)

## What I implemented

- New file `core/app/configs/bookmark_validation.py`: `validate_bookmark_payload(session, config, *, user)`.
  No-op for any `config.kind != "bookmark"`. For `kind="bookmark"`, resolves
  `config.bookmark.appId` via `items_repo.get_access_facts` + `can(..., action="read", ...)`;
  raises `HTTPException(422, "app not found")` if the item doesn't exist or isn't
  readable by the caller (same message for both, to avoid leaking existence —
  same convention as `dataset_validation.py`). If the item exists and is
  readable, fetches it via `items_repo.get_item` and rejects (same 422/message)
  if `resourceType` isn't `"app"` or `"dashboard"`.
- Wired into `core/app/configs/routes.py`:
  - New import: `from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload`,
    placed alphabetically next to the existing dataset import.
  - `create_config`: added `_validate_bookmark_payload(session, request.config, user=user)`
    right after the existing `_validate_dataset_payload` call.
  - `update_config_by_item`: added `_validate_bookmark_payload(session, config, user=user)`
    right after the existing `_validate_dataset_payload` call.
  - (Per the brief, `update_config` — the by-config-id PUT — was *not* touched;
    only `create_config` and `update_config_by_item` were in scope.)

Implementation is byte-for-byte the code given in the brief; no deviations.

## What I tested and results

New test file `core/tests/test_create_bookmark.py` (5 tests, exactly as specified
in the brief):

1. `test_create_bookmark_avec_app_existante_et_lisible` — bookmark targeting an
   app the caller owns → 201, and the created item's `resourceType` is `"bookmark"`.
2. `test_create_bookmark_app_inexistante_rejetee` — `appId` that doesn't exist → 422 `"app not found"`.
3. `test_create_bookmark_app_non_lisible_rejetee_avec_meme_message` — `appId`
   pointing to another user's private app → 422 `"app not found"` (same message
   as not-found, confirming no existence leak).
4. `test_create_bookmark_cible_un_kind_non_app_rejetee` — `appId` pointing to a
   `"map"` item (readable, but wrong resource type) → 422 `"app not found"`.
5. `test_update_bookmark_app_inexistante_rejetee` — same validation exercised
   through `PUT /configs/by-item/{id}`.

All 5 pass. Full core suite: `872 passed, 112 skipped` (no regressions;
`validate_bookmark_payload` is a no-op for every other `kind`). Import-linter
layered-architecture contract still passes: `Analyzed 125 files, 339
dependencies... Contracts: 1 kept, 0 broken`.

## TDD Evidence

**RED** — `cd core && uv run pytest tests/test_create_bookmark.py -v` (test file
written first, before `bookmark_validation.py` existed and before the routes.py
wiring):

```
tests/test_create_bookmark.py::test_create_bookmark_avec_app_existante_et_lisible PASSED [ 20%]
tests/test_create_bookmark.py::test_create_bookmark_app_inexistante_rejetee FAILED [ 40%]
tests/test_create_bookmark.py::test_create_bookmark_app_non_lisible_rejetee_avec_meme_message FAILED [ 60%]
tests/test_create_bookmark.py::test_create_bookmark_cible_un_kind_non_app_rejetee FAILED [ 80%]
tests/test_create_bookmark.py::test_update_bookmark_app_inexistante_rejetee FAILED [100%]
========================= 4 failed, 1 passed in 1.87s ==========================
```

Failures matched exactly what the brief predicted: `POST /configs` /
`PUT /configs/by-item/{id}` with `kind="bookmark"` returned 201/200
unconditionally (no semantic validation wired yet), so the four
"should-be-rejected" tests got a success status instead of 422. (The happy-path
test passed trivially since no validation was needed to make it succeed.)
Unrelated `procrastinate.exceptions.AppNotOpen` stack traces were logged during
item creation in this run — pre-existing noise from the embedding-job enqueue
path in the sqlite test setup (caught and logged elsewhere in
`app/items/repository.py`), not introduced by this change; it appears
identically before and after the fix, and throughout the rest of the suite.

**GREEN** — after creating `bookmark_validation.py` and wiring `routes.py`:

```
tests/test_create_bookmark.py::test_create_bookmark_avec_app_existante_et_lisible PASSED [ 20%]
tests/test_create_bookmark.py::test_create_bookmark_app_inexistante_rejetee PASSED [ 40%]
tests/test_create_bookmark.py::test_create_bookmark_app_non_lisible_rejetee_avec_meme_message PASSED [ 60%]
tests/test_create_bookmark.py::test_create_bookmark_cible_un_kind_non_app_rejetee PASSED [ 80%]
tests/test_update_bookmark_app_inexistante_rejetee PASSED [100%]
============================== 5 passed in 1.77s ===============================
```

Full suite: `cd core && uv run pytest -q` → `872 passed, 112 skipped in 53.96s`.

## Files changed

- `core/app/configs/bookmark_validation.py` (new)
- `core/app/configs/routes.py` (import + 2 call sites)
- `core/tests/test_create_bookmark.py` (new)

Commit: `c346c2d` — `feat(core): validate bookmark appId readability on create/update (SP-14m)`.

## Self-review

- Completeness: all 5 acceptance tests from the brief implemented and pass;
  both call sites (`create_config`, `update_config_by_item`) wired exactly as
  specified; `update_config` (by config_id) intentionally left untouched per
  the brief's scope (bookmarks aren't reachable through that route pattern in
  this plan).
- Quality: matches the existing `dataset_validation.py` / `_require_access`
  style in the same file; function name (`validate_bookmark_payload`) is the
  exact name Task 3 needs to wrap for the MCP tool.
- Discipline: no extra behavior added beyond the brief's literal code (e.g. no
  extra kind checks, no extra fields validated) — YAGNI respected.
- Testing: real HTTP requests through `TestClient` against a real (in-memory
  sqlite) DB and real `can()`/authorization logic — no mocks. Ran import-linter
  to confirm the new file doesn't violate the layered-architecture contract
  (it doesn't: `app.configs` already depends on `app.items`/`app.sharing`).
  `ruff` binary isn't installed in this environment (`uv run ruff` →
  "No such file or directory") so no lint pass was possible; the new file
  visually matches surrounding style (line length, import order, docstring
  conventions).

## Issues or concerns

- Several unrelated `.superpowers/sdd/*.md` files (`progress.md`,
  `task-1-brief.md`, `task-1-report.md`, `task-2-brief.md`) and an untracked
  `docs/superpowers/plans/2026-08-05-sp14m-bookmarks.md` showed up as
  modified/untracked in `git status` at the start of this task. None of these
  were touched by this task's work; only `core/app/configs/bookmark_validation.py`,
  `core/app/configs/routes.py`, and `core/tests/test_create_bookmark.py` were
  staged and committed. `task-2-report.md` itself already existed on disk with
  leftover content from an unrelated prior task (SP-14l's `run_analytics_query`
  MCP tool report) — it is overwritten here with this task's own report.
- No other concerns. All tests pass, no regressions, import-linter clean, no
  stray warnings.
