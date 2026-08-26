# Task 13 report — Valider la config restaurée avant de l'écrire

## What I implemented

1. **`core/app/configs/repository.py`** — new `get_revision_config(session, config_id, version) -> BuilderConfig | None`, reading a `ConfigRevision` row without writing anything (used by the route to validate the candidate before rollback). `BuilderConfig` was already imported in this module.

2. **`core/app/configs/routes.py`** — `rollback_config` now, between `_require_access` and the write:
   - loads the target revision via `repo.get_revision_config` (404 if the version doesn't exist — same behavior as before, just moved earlier);
   - runs the exact same 9-call validator sequence `update_config` runs (`_require_etl_enabled_for_pipeline`, `_require_export_enabled_for_report`, `_validate_extension_scope`, `_validate_dataset_payload`, `_validate_bookmark_payload`, `_validate_pipeline_payload`, `_validate_alert_payload`, `_validate_report_payload`, `_validate_tileset3d_payload`, `_validate_terrain3d_payload`);
   - catches `HTTPException` and re-raises as 422 with a message naming the rejected version and the original detail;
   - only then calls `repo.rollback_config` to actually write version N+1.

3. **`core/tests/test_configs_rollback_validation.py`** (new) — two tests:
   - `test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected`: creates a valid `kind="alert"` config referencing a dataset item, updates it to v2 (still valid), deletes the dataset item, then rolls back to v1 → expects 422 with `"dataset not found"` in the detail, and confirms via `GET` that `version` is still 2 (nothing written).
   - `test_rollback_to_a_still_valid_version_succeeds_and_bumps_version` (non-regression): same setup but without deleting the dataset → rollback to v1 succeeds (200), version becomes 3.

4. **`core/tests/test_configs_extension_permissions.py`** (modified, see "Deviation" below) — renamed/rewrote `test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope` to `test_rollback_is_rejected_if_it_would_now_violate_a_narrowed_scope`, flipping its final assertion from `200` to `422`.

## Deviation from the brief's file list — explained

The brief listed exactly three files to touch (`routes.py`, `repository.py`, the new test). While running the full suite I found this pre-existing test in `test_configs_extension_permissions.py`:

```python
def test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope(client):
    ...
    # Mais rollback restaure v1 tel quel, sans revalidation contre le scope
    # courant — comportement volontaire (cf. spec, §Hors périmètre).
    rollback = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 200
```

This codified a **deliberate** decision from `docs/superpowers/specs/2026-07-13-sp8c-widget-tiers-durcissement-design.md` §Hors périmètre: *"Revalidation du scope de permissions au `rollback_config` — restaure une révision déjà validée au moment de sa création ; un scope qui se resserrerait entre-temps est un cas marginal, non traité ici."*

The SP-23 design spec (`docs/superpowers/specs/2026-08-21-sp23-quatre-bouchons-design.md`, §3.4, lines 227-240) explicitly lists **"portée d'extension"** as one of the eight validators the rollback route must now run, and gives the reasoning for reversing the SP-8c decision (the route becomes reachable by real users via Task 16, so a theoretical gap becomes real). The task-13 brief's own Step 3 code block includes `_validate_extension_scope(...)` in the sequence, which directly implements this reversal — the plan author evidently didn't cross-check the SP-8c test that locked in the opposite contract.

Given the SP-23 spec is explicit, dated the same day, and directly reasoning about this exact route, I treated it as authoritative over the older SP-8c decision and updated the outdated test to match the new, intended contract (I did not delete it — I kept it as a live regression test for the *new* behavior, updated its comments to explain the supersession). Without this change the full suite would fail (1 failed), which the plan's own gate requires to be 0.

I did not touch the SP-8c spec document itself — spec files are point-in-time historical records in this repo's convention; the supersession is documented in the SP-23 spec (already existing) and now in the test's own comment.

## What I tested and test results

- New test file alone (RED, before implementation — verified via `git stash` of `routes.py`/`repository.py`):
  ```
  tests/test_configs_rollback_validation.py::test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected FAILED
  tests/test_configs_rollback_validation.py::test_rollback_to_a_still_valid_version_succeeds_and_bumps_version PASSED
  1 failed, 1 passed
  ```
  (the deleted-dataset scenario failed because rollback answered 200 instead of 422 — the non-regression scenario already passed pre-change, as expected, since it doesn't exercise the gap.)

- New test file + `test_configs_models.py` (GREEN, after implementation):
  ```
  tests/test_configs_rollback_validation.py::test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected PASSED
  tests/test_configs_rollback_validation.py::test_rollback_to_a_still_valid_version_succeeds_and_bumps_version PASSED
  tests/test_configs_models.py::test_can_persist_config_and_revision PASSED
  tests/test_configs_models.py::test_base_metadata_has_both_tables PASSED
  4 passed
  ```

- `test_configs_extension_permissions.py` alone: 7 passed (including the updated rollback/extension-scope test).

- Full core suite (`cd core && uv run pytest -q`): **1673 passed, 153 skipped, 0 failed** (271.98s). Reference before this task was 1671 passed / 153 skipped / 0 failed — the +2 matches exactly the two new tests added (the extension-permissions file's test count is unchanged, it was a rename+flip, not an addition).

## TDD Evidence

**RED** — command: `cd core && uv run pytest tests/test_configs_rollback_validation.py -v` (run with `app/configs/routes.py` and `app/configs/repository.py` temporarily reverted via `git stash`):
```
tests/test_configs_rollback_validation.py::test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected FAILED
tests/test_configs_rollback_validation.py::test_rollback_to_a_still_valid_version_succeeds_and_bumps_version PASSED
1 failed, 1 passed in 5.92s
```
Log line confirming the wrong status: `POST http://testserver/configs/.../rollback "HTTP/1.1 200 OK"` where the test asserts 422. Expected failure for the right reason: without the validation step, rollback happily restores a version referencing a now-deleted dataset.

**GREEN** — command: `cd core && uv run pytest tests/test_configs_rollback_validation.py tests/test_configs_models.py -v` (after `git stash pop`, implementation restored):
```
tests/test_configs_rollback_validation.py::test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected PASSED
tests/test_configs_rollback_validation.py::test_rollback_to_a_still_valid_version_succeeds_and_bumps_version PASSED
tests/test_configs_models.py::test_can_persist_config_and_revision PASSED
tests/test_configs_models.py::test_base_metadata_has_both_tables PASSED
4 passed in 5.81s
```

## Files changed

- `core/app/configs/routes.py` — `rollback_config` now validates the candidate revision before writing (see diff summary above).
- `core/app/configs/repository.py` — new `get_revision_config` helper.
- `core/tests/test_configs_rollback_validation.py` — new, 2 tests.
- `core/tests/test_configs_extension_permissions.py` — 1 existing test updated to match the SP-23-superseded contract (see "Deviation" above).

Not touched, left as pre-existing untracked/modified noise unrelated to this task (explicitly excluded from `git add`): `.superpowers/sdd/task-13-brief.md`, `deploy/postgis/pg_hba.conf`.

## Verification of the eight validator functions' exception types (Step 3 caveat)

Read all eight (`app/configs/dataset_validation.py`, `bookmark_validation.py`, `pipeline_validation.py`, `alert_validation.py`, `report_validation.py`, `tileset3d_validation.py`, `terrain3d_validation.py`, plus `_validate_extension_scope`'s wrapper around `validate_extension_permissions`/`ExtensionPermissionError` in `routes.py`) before writing the `except` clause, as instructed. All eight raise `HTTPException` only (with varied status codes 400/403/422) — `_validate_extension_scope` itself catches the module-specific `ExtensionPermissionError` and converts it to `HTTPException(400, ...)`, so a plain `except HTTPException` in `rollback_config` is correct and sufficient; no widening to `(HTTPException, ValueError)` was needed.

## Self-review findings

- Confirmed via commit-log semantics: `_require_access` still runs first, so an unauthorized/unowned-item rollback still returns 404/403 before touching validation, matching `test_rollback_by_stranger_returns_404`.
- Confirmed `test_rollback_missing_returns_404` (target version doesn't exist) still passes: `get_revision_config` returns `None` → 404, same as before (just raised earlier than the old `repo.rollback_config(...)` call).
- Confirmed `test_repository.py`'s two `rollback_config` tests are unaffected — I didn't change `repository.rollback_config`'s behavior, only added a new read-only helper next to it.
- Test output is pristine for the two focused runs (no warnings). The full-suite run does emit some `ResourceWarning: unclosed database` lines from unrelated pre-existing sqlite fixtures elsewhere in the suite (also present before this task, not touched here) — none from my new file.
- No overbuilding: implementation matches the brief's Step 3/4 code blocks verbatim, only deviation is the necessary test-contract update explained above.

## Issues or concerns

- The one substantive concern is the deviation described above (updating `test_configs_extension_permissions.py`). I'm confident it's correct given the SP-23 spec explicitly names "portée d'extension" as one of the eight validators to re-run on rollback and explains the reversal of the SP-8c decision — but flagging it explicitly since it touches a file outside the brief's stated scope and reverses a previously-deliberate, documented behavior.
