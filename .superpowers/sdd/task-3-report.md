# Task 3 report — `app/configs/alert_validation.py`

## What was implemented

`core/app/configs/alert_validation.py` (new): `validate_alert_payload(session, config, *, user) -> None`.
Mirrors `app.configs.bookmark_validation.validate_bookmark_payload` exactly:
no-op if `config.kind != "alert"`; otherwise resolves `config.alert.datasetItemId`
via `items_repo.get_access_facts` + `app.sharing.authorization.can(action="read")`,
raising `HTTPException(422, detail="dataset not found")` if the item is missing
or not readable (same message for both, to avoid leaking existence — same
convention as bookmark_validation), then re-fetches via `items_repo.get_item`
and raises the same 422/"dataset not found" if `target.resourceType != "dataset"`.

Wired into `core/app/configs/routes.py`: one new import
(`from app.configs.alert_validation import validate_alert_payload as _validate_alert_payload`)
and one new call, `_validate_alert_payload(session, ..., user=user)`, added
alongside the three existing `_validate_*_payload` calls in `create_config`,
`update_config`, and `update_config_by_item`.

Code matches the brief's Step 3 block verbatim — confirmed by reading the
current `bookmark_validation.py` first, which the brief's code mirrors
character-for-character (only the field name `datasetItemId`/`payload.alert`
and the error-context comments differ).

## Discrepancy found and fixed (test fixture, not `bookmark_validation.py`/`routes.py`)

`bookmark_validation.py` and `routes.py` matched the brief's assumptions
exactly — no divergence there. The divergence was in the brief's **own test
fixture** (`_client_and_user`), which the brief dictated verbatim:

The fixture created a user `oidc_sub="a"`/`username="alice"` and set
`Authorization: Bearer mock:alice`, assuming mock-mode auth would resolve the
acting user from the token content. It doesn't: `app.auth.dependency.
get_current_user`'s mock branch always resolves to a **fixed** identity
(`oidc_sub="mock-sub"`, `username="mockuser"`), ignoring everything after
`"Bearer "` beyond the prefix check. Confirmed against `test_routes.py`'s
`client_with_real_auth` fixture (the only other test in the suite that drives
mock auth through the real HTTP path rather than via `dependency_overrides`),
whose comment states this explicitly.

Effect: in the brief's literal fixture, items created with `owner_id=user.id`
("alice") were never owned by the actual acting HTTP user ("mockuser"), so
`can(action="read")` failed even for a genuinely readable dataset — the third
test (`succeeds_against_a_readable_dataset`) failed with 422 "dataset not
found" for the *wrong* reason (ownership mismatch), and the second test
(`rejects_a_non_dataset_item`) would have passed for the wrong reason too
(masking the resourceType check behind an ownership failure).

Fix: changed the fixture to create the user with `oidc_sub="mock-sub"`,
`username="mockuser"` (matching `get_current_user`'s mock resolution exactly),
so items created with `owner_id=user.id` are genuinely owned by the acting
request identity. No production code was affected — `alert_validation.py`
and the `routes.py` wiring are unchanged from the brief's Step 3 code block.

## Tests and results

- `tests/test_alert_validation.py` (3 new tests, brief's Step 1 body plus the
  fixture fix above): `3 passed`.
- Regression, brief-specified: `tests/test_configs_models.py`: `2 passed`.
- Broader regression (configs/routes/alert/pipeline/bookmark/mcp-configs):
  `tests/test_routes.py tests/test_create_bookmark.py tests/test_configs_models.py
  tests/test_alert_validation.py tests/test_alert_condition.py
  tests/test_alert_config_schema.py tests/test_pipeline_config_validation.py
  tests/test_mcp_tools_configs.py tests/test_mcp_tools_bookmark_create.py`:
  `84 passed`.
- Full suite: `1235 passed, 131 skipped` (skips are the docker-gated postgis
  tests, consistent with the documented baseline in CLAUDE.md).

All runs used:
`PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q ...`

## TDD evidence

**RED** (before implementing `alert_validation.py` / wiring `routes.py`, test
file already written):
```
FAILED tests/test_alert_validation.py::test_create_alert_rule_rejects_a_nonexistent_dataset
FAILED tests/test_alert_validation.py::test_create_alert_rule_rejects_a_non_dataset_item
2 failed, 1 passed in 2.14s
```
(the third test passed by accident, both rejections returned 201 — as the
brief predicted for the RED state, before either the implementation or the
fixture fix.)

**Intermediate** (implementation + wiring done, fixture bug not yet fixed):
```
FAILED tests/test_alert_validation.py::test_create_alert_rule_succeeds_against_a_readable_dataset
1 failed, 2 passed in 2.12s
```
Diagnosed via a standalone repro script hitting `/configs` directly and
inspecting the JSON body (`{"detail": "dataset not found"}` on a genuinely
readable dataset) — traced to the mock-auth identity mismatch described
above.

**GREEN** (after fixing the fixture's user identity):
```
tests/test_alert_validation.py: 3 passed in 2.03s
```

## Files changed

- `core/app/configs/alert_validation.py` (new) — matches brief's Step 3 verbatim.
- `core/app/configs/routes.py` — 1 import + 3 call sites, matches brief's wiring verbatim.
- `core/tests/test_alert_validation.py` (new) — brief's Step 1 test bodies verbatim; only the `_client_and_user` fixture's user identity (`oidc_sub`/`username`) was changed from `"a"`/`"alice"` to `"mock-sub"`/`"mockuser"` to match real mock-auth resolution.

## Self-review

- Completeness: all 3 tests from the brief pass, using the real HTTP+DB path (`TestClient` + SQLite, no `get_current_user` override) as specified.
- Quality: `alert_validation.py` matches `bookmark_validation.py`'s style exactly — same imports, same docstring shape, same two-step access-facts-then-resourceType-check structure, same "same message for both failure cases" convention and comment.
- Discipline: no validation added beyond what the brief specifies. Did not touch `app/configs/schemas.py` or any file outside the declared scope (`alert_validation.py`, `routes.py`'s 3 call sites + 1 import, `test_alert_validation.py`).
- Testing: pristine output on the new test file, the brief's regression file, a broader regression sweep, and the full suite (1235 passed, 131 skipped — skip count and total match the documented baseline, no new skips or failures introduced).

## Issues / concerns

- The brief's dictated test fixture (`_client_and_user`) had a latent bug: it assumed mock-mode auth parses the identity from the bearer token content, but `get_current_user`'s mock branch is hardcoded to a single fixed identity. This is a fixture-only issue (already flagged as a risk pattern by Tasks 1 and 2's "plan's dictated code" discrepancies) — fixed by aligning the fixture's user identity with the real mock-mode resolution. No implementation or wiring code needed to change; `alert_validation.py` and `routes.py` are exactly as specified.
- No other discrepancies found. `bookmark_validation.py` and the 3 `routes.py` call sites matched the brief's assumptions exactly on read.
