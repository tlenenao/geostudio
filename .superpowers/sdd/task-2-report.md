# Task 2 report — items repository, schemas, and read/update endpoints

## What was implemented

Followed the brief's file contents verbatim (no deviations needed — the installed
FastAPI/Starlette `TestClient` API matched what the brief assumed).

- `core/app/items/schemas.py` — `ItemRead`, `ItemPage`, `ItemUpdatePatch` (Pydantic).
- `core/app/items/repository.py` — `create_item`, `get_item`, `list_items`, `update_item`,
  plus a private `_to_read()` mapper. `configId` is hardcoded to `None` in `_to_read()`
  with a comment explaining why (layering: `app.items` must never import `app.configs`;
  matches the shell's existing `toItem()` behavior, so no regression).
- `core/app/items/routes.py` — `GET /items`, `GET /items/{item_id}`, `PATCH /items/{item_id}`,
  all behind `Depends(get_current_user)`. PATCH writes an audit log entry
  (`item.publish` / `item.unpublish` / `item.update` depending on `isPublished`).
- `core/app/main.py` — added `from app.items import routes as items_routes` and
  `app.include_router(items_routes.router)`.
- `core/tests/test_items_repository.py` — 7 tests (create/get, missing, scope
  mine/public/shared/all with search+type filter, update).
- `core/tests/test_items_routes.py` — 5 tests (get found/404, list default scope,
  patch found/404).

Did not touch `app/configs/*` or `core/tests/test_routes.py`, per instructions.

## TDD evidence

1. Wrote schemas first (no test dependency for pure Pydantic models — brief doesn't
   ask for a schema-only test step).
2. Wrote `test_items_repository.py`, ran it: failed with
   `ImportError: cannot import name 'repository' from 'app.items'` — confirmed red.
3. Wrote `repository.py`, ran it again: `7 passed`.
4. Wrote `test_items_routes.py`, ran it: 3 of 5 failed with `404` where `200` expected
   (routes not registered yet) — confirmed red. (2 already passed: the two 404-expecting
   tests, since undefined routes 404 by default — expected and consistent with the brief's
   "FAIL — /items routes don't exist yet (404s where 200s are expected)".)
5. Wrote `routes.py`, registered router in `main.py`, ran again: `5 passed`.

## Full suite / lint-imports

`cd core && uv run pytest`:
```
14 failed, 71 passed in 9.91s
```
All 14 failures are in `tests/test_routes.py` (the pre-existing GeoNode-stub creation
path tests noted as Task 3's territory — same 14 test names/count as called out in the
task instructions, e.g. `test_create_config_creates_item_and_returns_201`,
`test_get_config_returns_it`, `test_put_updates_and_bumps_version`, etc., all failing with
`sqlalchemy.exc.IntegrityError` on the `configs.item_id` FK). Nothing in this task's diff
touches `app/configs` or `test_routes.py`, so this count is unchanged from before this
task's changes. 71 passed includes all 7 new repository tests + all 5 new route tests
plus the full pre-existing green suite.

`cd core && uv run lint-imports`:
```
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

## Files changed

- `core/app/items/schemas.py` (new)
- `core/app/items/repository.py` (new)
- `core/app/items/routes.py` (new)
- `core/app/main.py` (modified: +2 lines — import and `include_router`)
- `core/tests/test_items_repository.py` (new)
- `core/tests/test_items_routes.py` (new)

Commit: `244507f feat(core): items repository, schemas, and GET/PATCH endpoints`

## Self-review findings

- Endpoint shapes match the brief exactly: `GET /items` returns `ItemPage`
  (`items`, `total`, `page`, `pageSize`), `GET /items/{id}` and `PATCH /items/{id}`
  return `ItemRead`. Query params `q`, `type`, `scope`, `page`, `pageSize` all present
  with the brief's defaults (`scope="all"`, `page=1`, `pageSize=12`).
- `configId` verified always `None`: only set in `_to_read()`, unconditionally, and
  `grep -r "app.configs" core/app/items/` returns nothing — no import of `app.configs`
  anywhere in the `items` package.
- Pre-existing `test_routes.py` failures: exactly 14 before and after, same tests.
- `uv run pytest` and `uv run lint-imports` output both pristine (no warnings besides
  the expected `GEONODE_BASE_URL/GEONODE_TOKEN not set` info log, which is pre-existing
  and unrelated to this task).

## Concerns

None. No workarounds needed; the layering constraint (items must not import configs)
was straightforward to satisfy per the brief's design (configId always None).
