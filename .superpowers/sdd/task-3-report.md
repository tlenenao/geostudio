# Task 3 report: Wire item creation/deletion into `configs`; remove GeoNode from create/delete paths

## What I implemented

1. Rewrote `core/tests/test_routes.py` per the brief:
   - Replaced the `client` fixture: no more `StubItemClient`/`routes.get_item_client` override;
     provisions a real tenant + user (`app.tenants.repository.get_or_create_default_tenant`,
     `app.users.repository.get_or_create_user`) and overrides `get_current_user` to return that
     user directly.
   - Removed `"owner": "alice"` from every `client.post("/configs", ...)` body (including the
     ones in `test_map_config_round_trips_through_create_and_get`,
     `test_map_config_can_be_updated`, `test_put_config_by_item_updates_map`, and the two
     `client_with_real_auth` tests — not explicitly spelled out in the brief's diff but required
     for consistency, since those calls would otherwise 422 on the now-required-absent `owner`
     field).
   - Replaced `test_create_config_creates_item_and_returns_201` with
     `test_create_config_creates_a_real_item_owned_by_the_authenticated_user`, which loads the
     `Item` row directly and asserts `owner_id == client.user.id`.
   - Replaced the two stub-based delete tests with `test_delete_config_removes_config_and_item`,
     `test_delete_by_item_removes_config_and_item` (both now assert `session.get(Item, item_id)
     is None` instead of `client.stub.deleted == [...]`).
   - Added `test_delete_item_directly_removes_config_and_item` and
     `test_delete_item_missing_returns_404` for the new `DELETE /items/{item_id}` route.
   - Extended `test_create_config_writes_audit_log` to assert both `"config.create"` and
     `"item.create"` are present in the audit action set.
   - Also updated the `client_with_real_auth` fixture: dropped its `StubItemClient` instantiation
     and the `routes.get_item_client` override (that attribute no longer exists on
     `configs.routes`), keeping `get_current_user` un-overridden as before — this fixture's whole
     point is to exercise the real auth dependency end-to-end.

2. Ran `uv run pytest tests/test_routes.py -v` against the untouched (Task 1/2) `configs/routes.py`
   to confirm RED (see evidence below).

3. Rewrote `core/app/configs/routes.py` exactly per the brief's file content:
   - `CreateConfigRequest` no longer has an `owner` field.
   - `create_config` calls `items_repo.create_item(session, tenant_id=user.tenant_id,
     owner_id=user.id, resource_type=request.config.kind, title=request.title)` then
     `repo.create_config(session, request.config, item_id=item.id)`, and writes both a
     `config.create` and an `item.create` audit row.
   - Added `_delete_config_and_item(session, config_id, item_id)`: deletes `ConfigRevision` rows
     for the config, deletes the `Config` row, deletes the `Item` row, commits.
   - `delete_config`, `delete_config_by_item`, and the new `delete_item` (`DELETE
     /items/{item_id}`) all resolve the config via `repo.get_config`/`repo.get_config_by_item`,
     call `_delete_config_and_item`, and write both `config.delete` and `item.delete` audit rows.
   - No import of `app.geonode` remains in this file; `get_item_client`/`ItemClient`/
     `StubItemClient` are gone.

4. Rewrote `core/app/main.py` exactly per the brief: removed the `logging` import, the
   `geonode_url`/`geonode_token` block, and the `GeoNodeItemClient` conditional wiring; kept
   `items_routes` import/registration (already present from Task 2) alongside `configs_routes` and
   `auth_routes`.

5. `git rm core/tests/test_main_wiring.py` — it exercised the now-removed
   `GeoNodeItemClient`/`StubItemClient` conditional wiring in `main.py`.

6. Ran `cd core && uv run pytest`: full suite (85 tests) green, 0 failures.

7. Ran `cd core && uv run pytest tests/test_geonode.py tests/test_geonode_http.py -v`: both files'
   4 tests pass unaffected (they exercise `app/geonode.py` directly).

8. Ran `cd core && uv run lint-imports`: "layered architecture KEPT", "Contracts: 1 kept, 0
   broken."

9. Committed as `4d3101c feat(core): create/delete items+configs in one local transaction; remove
   GeoNode from these paths`.

## TDD evidence

### RED (before rewriting `configs/routes.py`/`main.py`, after rewriting the tests)

`uv run pytest tests/test_routes.py -v` → **16 failed, 7 passed**. Representative failures:

```
FAILED tests/test_routes.py::test_create_config_creates_a_real_item_owned_by_the_authenticated_user
FAILED tests/test_routes.py::test_get_config_returns_it
FAILED tests/test_routes.py::test_put_updates_and_bumps_version
FAILED tests/test_routes.py::test_revisions_listed
FAILED tests/test_routes.py::test_rollback_restores_revision
FAILED tests/test_routes.py::test_rollback_missing_returns_404
FAILED tests/test_routes.py::test_delete_config_removes_config_and_item
FAILED tests/test_routes.py::test_get_config_by_item
FAILED tests/test_routes.py::test_delete_by_item_removes_config_and_item
FAILED tests/test_routes.py::test_delete_item_directly_removes_config_and_item
FAILED tests/test_routes.py::test_delete_item_missing_returns_404
FAILED tests/test_routes.py::test_map_config_round_trips_through_create_and_get
FAILED tests/test_routes.py::test_map_config_can_be_updated
FAILED tests/test_routes.py::test_put_config_by_item_updates_map
FAILED tests/test_routes.py::test_create_config_writes_audit_log
FAILED tests/test_routes.py::test_create_config_with_bearer_token_succeeds_in_mock_mode
```

Root cause of most of these: `CreateConfigRequest` on the old routes.py still required `owner`
in the body (`422 Unprocessable Entity — Field required: body.owner`), so `_create()`'s
`assert response.status_code == 201` failed and cascaded through every test that used `_create`
or a bare `client.post("/configs", ...)`. This is a larger RED set than the plan's mentioned "14
known failures" because I also removed `owner` from bodies in tests not explicitly enumerated
in the brief's diff (map-config tests, real-auth tests) for consistency — those legitimately
needed the same fix and were not part of the original 14.

### GREEN (after rewriting `configs/routes.py` and `main.py`)

`uv run pytest tests/test_routes.py -v` → **23 passed**.

`uv run pytest` (full suite) → **85 passed**, no warnings.

`uv run pytest tests/test_geonode.py tests/test_geonode_http.py -v` → **4 passed** (unaffected).

`uv run lint-imports` → clean, "layered architecture KEPT", "Contracts: 1 kept, 0 broken."

## Files changed

- `core/app/configs/routes.py` — rewritten per brief.
- `core/app/main.py` — rewritten per brief (GeoNode wiring removed).
- `core/tests/test_routes.py` — rewritten per brief, plus consistency fixes to the
  `client_with_real_auth` fixture and additional `"owner"` removals in map-config tests.
- `core/tests/test_main_wiring.py` — deleted (`git rm`).

Commit: `4d3101c feat(core): create/delete items+configs in one local transaction; remove GeoNode
from these paths`.

## Self-review findings

- `POST /configs` no longer accepts `owner`: confirmed — `CreateConfigRequest` has only `title`
  and `config` fields; `grep -n "owner" app/configs/routes.py` only matches the
  `owner_id=user.id` keyword argument passed to `items_repo.create_item`.
- Ownership genuinely comes from `Depends(get_current_user)`: confirmed — `create_config`'s
  `user: User = Depends(get_current_user)` parameter feeds `owner_id=user.id` directly; no other
  source of an owner identity exists in the route.
- All three delete routes (`DELETE /configs/{id}`, `DELETE /configs/by-item/{id}`, `DELETE
  /items/{id}`) call the shared `_delete_config_and_item`, which explicitly deletes
  `ConfigRevision` rows, then the `Config` row, then the `Item` row, in that order, in one
  transaction (single `session.commit()` at the end) — verified by tests that query the DB
  directly afterward (`session.get(Item, item_id) is None`, and a `GET` on the deleted config
  returning 404), not just code inspection.
  - Note: this implementation does not actually rely on the FK cascade to remove `configs` when
    `items` is deleted — it deletes `Config` explicitly before deleting `Item`, matching the
    brief's code exactly. The cascade (`ondelete="CASCADE"` on `configs.item_id`) exists as a
    defensive DB-level backstop but isn't exercised as the primary deletion mechanism in this
    code path. I did not deviate from the brief's given code, so this is a design characteristic
    inherited from the plan rather than something I introduced.
- `GeoNodeItemClient`/`StubItemClient`/`get_item_client` are genuinely gone from
  `configs/routes.py` and `main.py`: confirmed via
  `grep -n "GeoNode\|StubItemClient\|get_item_client\|geonode" app/configs/routes.py app/main.py`
  → no matches (exit code 1).
- `uv run pytest` output is pristine: 85 passed, 0 failures, no warnings in the summary.

## Concerns

None blocking. One minor observation already noted above: the delete helper explicitly deletes
`Config` rather than solely relying on the FK cascade from `Item` deletion, so the
FK-cascade-enforcement work from Task 1 (SQLite FK pragma) is present as a safety net in this
code path but not the mechanism actually exercised by these specific delete routes. This matches
the brief's exact prescribed code, so I did not alter it.

## Fix: single-commit-per-request transaction boundary

Addresses the Important review finding: `POST /configs` (and every other
mutating route) issued multiple independent `session.commit()` calls per
request, so a failure between `create_item` and `create_config`/`write_audit`
left a permanently orphaned `Item` with no rollback. Reworked the codebase to
**one commit per request, owned at the boundary**: repositories/writers only
`flush()`; a single shared context manager commits once on success and rolls
back the whole transaction on any exception.

### Files changed and why

Infrastructure:
- `core/app/db.py` — added `request_scoped_session(session_factory)` context
  manager (yields a session, commits on clean exit, rolls back + re-raises on
  any exception). Added `from contextlib import contextmanager`.
- `core/app/main.py` — real `get_session` now delegates to
  `request_scoped_session(session_factory)` instead of a bare
  `with session_factory()`.

Repository/writer functions (`session.commit()` → `session.flush()`, keeping
`session.refresh(...)` which works correctly after a flush within the same
open transaction):
- `core/app/tenants/repository.py` — `get_or_create_default_tenant`
- `core/app/users/repository.py` — `get_or_create_user`
- `core/app/audit/writer.py` — `write_audit` (returns None; now `add` + `flush`)
- `core/app/items/repository.py` — `create_item`, `update_item`
- `core/app/configs/repository.py` — `create_config`, `update_config`,
  `rollback_config`, `delete_config`
- `core/app/configs/routes.py` — `_delete_config_and_item` helper (dropped its
  internal commit; the request boundary now owns it)

Test fixtures — `override_session()` now uses `request_scoped_session(Session)`
so tests exercise the identical boundary logic as production:
- `core/tests/test_routes.py` (both `client` and `client_with_real_auth`)
- `core/tests/test_items_routes.py`
- `core/tests/test_me.py`

Cross-session test commits — tests that provision data in one `with Session()`
block and verify in a separate block now `commit()` at the end of the first
block, standing in for "a prior successful request":
- `core/tests/test_routes.py` (`client` setup block)
- `core/tests/test_items_routes.py` (`client` setup block + `_seed_item` helper)
- `core/tests/test_me.py` (`client` setup block)
- `core/tests/test_tenants.py`, `core/tests/test_users.py`,
  `core/tests/test_audit.py`

No changes needed (confirmed by reading each):
- `core/tests/test_repository.py`, `core/tests/test_items_repository.py` — use a
  single shared `session` throughout; `flush()` makes writes visible to later
  reads in the same transaction. (`test_repository.py::_make_item` keeps its own
  explicit `commit()`, which is harmless.)
- `core/tests/test_auth.py` — calls `get_current_user` directly with a single
  session and never crosses a session boundary.
- `core/tests/test_configs_models.py`, `test_items_models.py`, `test_db.py` —
  already `commit()` explicitly in their first block.

### New atomicity regression test

`core/tests/test_routes.py::test_create_config_is_atomic_when_a_later_step_fails`
— monkeypatches `routes.repo.create_config` to raise `RuntimeError` *after*
`create_item` has already run, POSTs `/configs`, asserts the exception
propagates, then opens a fresh session and asserts `select(Item)` returns `[]`
(no orphaned Item survived — the whole request rolled back).

Meaningfulness verified: temporarily restoring `create_item`'s internal
`session.commit()` makes this test FAIL (orphan Item persists); with the
flush-based fix it PASSES.

```
=== atomicity test ===
tests/test_routes.py::test_create_config_is_atomic_when_a_later_step_fails PASSED
1 passed in 0.47s

=== same test with create_item committing internally (regression check) ===
FAILED tests/test_routes.py::test_create_config_is_atomic_when_a_later_step_fails
tests/test_routes.py:297: AssertionError   # session.scalars(select(Item)).all() != []
1 failed in 0.51s
```

### Full suite

```
86 passed in 2.03s
```

### lint-imports

```
Analyzed 26 files, 43 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

### Concerns / notes for later tasks

- `flush()`-then-`refresh()` works for every model here because all
  primary keys and server-side defaults in play (uuid hex PKs assigned in
  Python; `created_at`/`current_version` etc.) are populated at flush time on
  SQLite and Postgres alike — no value required a real commit to become
  visible. No workaround was needed.
- **Task 4 (thumbnails) implementer:** `set_thumbnail_key` does not exist on
  this branch yet, so it was not touched. Any new repository/writer function
  you add MUST follow this convention: `flush()` (never `commit()`) and let the
  request boundary own the transaction. If you add a test that provisions data
  in one session and verifies in another, add an explicit `session.commit()` at
  the end of the first block.
- `configs/repository.py::delete_config` is only reachable from
  `test_repository.py` (the delete routes use the `_delete_config_and_item`
  helper), but it was fixed for consistency rather than left as a stale
  commit-based function.
