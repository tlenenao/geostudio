# Task 1 report — items table, migration, layering, cascade-safe deletion plumbing

## Status: DONE_WITH_CONCERNS

Task 1 is implemented exactly per `task-1-brief.md`'s 13 steps and is committed. However,
`cd core && uv run pytest` for the **whole repo** does not fully pass: 14 tests in
`tests/test_routes.py` now fail. This is documented below in detail — it is a known,
plan-anticipated consequence of doing this schema change before Task 3 lands, not a bug
introduced by guesswork. Flagging as a concern rather than silently declaring DONE, since
my instructions asked me to confirm the full suite passes.

## What was implemented (steps 1-13 of the brief)

1. **`core/tests/test_items_models.py`** — written verbatim from the brief (2 tests).
2. Verified it failed with `ModuleNotFoundError: No module named 'app.items'` before the model existed.
3. **`core/app/items/__init__.py`** (empty) and **`core/app/items/models.py`** — the `Item` model, verbatim from the brief: `id, tenant_id, owner_id, resource_type, title, abstract, keywords, thumbnail_key, is_published, created_at, updated_at`.
4. Registered `app.items.models` in `core/app/db.py`'s `init_db()` and in `core/alembic/env.py`.
5. **`core/app/db.py`**: restructured `make_engine()` so both the in-memory and file/Postgres branches fall through to a shared `if engine.dialect.name == "sqlite": @event.listens_for(engine, "connect") PRAGMA foreign_keys=ON` block — no duplicated `StaticPool` logic.
6. **`core/app/configs/models.py`**: `Config.item_id` changed from `Mapped[str | None]` (nullable, no constraint) to `Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)`. `ForeignKey` was already imported in this file.
7. **`core/pyproject.toml`**: `app.items` inserted into the `import-linter` layers list between `app.configs` and `app.auth`; also added `"app.db -> app.items.models"` to `ignore_imports` (needed because `init_db()`'s local import of `app.items.models` is a `app.db -> app.items` edge that the layers contract would otherwise flag, exactly like the existing entries for `configs`/`audit`/`tenants`/`users`).
8. **`core/alembic/versions/0005_items.py`** — written verbatim from the brief: creates `items`, drops and re-adds `configs.item_id` as the new FK.
9. Verified `test_items_models.py` passes (2/2).
10. Fixed the tests broken by the now-enforced FK (see below).
11. `uv run lint-imports` → `Contracts: 1 kept, 0 broken.`
12. Postgres round-trip: `alembic upgrade head` then `alembic downgrade base` against a throwaway `postgis/postgis:16-3.4` container — both exited 0 (output below).
13. Committed (`cf47042`).

## TDD evidence

```
$ uv run pytest tests/test_items_models.py -v      # before model existed
ModuleNotFoundError: No module named 'app.items'
1 error during collection

$ uv run pytest tests/test_items_models.py -v      # after model written
tests/test_items_models.py::test_can_persist_and_load_item PASSED
tests/test_items_models.py::test_base_metadata_has_items_table PASSED
2 passed
```

## Files changed

- `core/app/items/__init__.py` (new, empty)
- `core/app/items/models.py` (new) — `Item` model only, no repository/routes (per instructions, that's Task 2)
- `core/alembic/versions/0005_items.py` (new) — migration 0005
- `core/alembic/env.py` — registers `app.items.models`
- `core/app/db.py` — SQLite FK-pragma wiring + `items` import in `init_db()`
- `core/app/configs/models.py` — `item_id` is now `Mapped[str]`, real FK, `ondelete="CASCADE"`
- `core/pyproject.toml` — `import-linter` layers + `ignore_imports` entry
- `core/tests/test_items_models.py` (new)
- `core/tests/test_repository.py` — every `create_config(...)` call now inserts a real `Item` row (via a new `_make_item(session, item_id)` helper) before referencing that `item_id`; `item_id=None` placeholders replaced with real ids (`"item-1"`, `"item-7"`)
- `core/tests/test_configs_models.py` — `Config(...)` construction now creates a tenant/user/`Item` first via `session.flush()` (see "why `flush()`" below), and uses `item_id="item-1"` instead of `None`

`core/uv.lock` unchanged — no new dependency was added in this task.

## Why every `test_repository.py`/`test_configs_models.py` fix needed a real `Item` row (not just a non-null string)

The brief's Step 6 initially suggests a placeholder string is enough, then self-corrects:
since Step 5 turns SQLite FK enforcement fully on, `item_id="item-1"` with no matching
`items.id` row raises `IntegrityError` too, not just `item_id=None`. I followed the
brief's corrected instruction: for every `Config`-constructing call site, insert a real
`Item` row (tenant + user + `Item(...)`, same fixture pattern as `test_items_models.py`)
before creating the `Config`.

One subtlety not spelled out in the brief: in `test_configs_models.py`, `Item` and `Config`
are added to the *same* session without an ORM `relationship()` between them (just a raw
FK column). Without an explicit `session.flush()` between `session.add(item)` and
`session.add(config)`, SQLAlchemy's unit-of-work was not guaranteed to insert `items`
before `configs` in the same flush, and the test failed with the exact same
`IntegrityError` even though the `Item` row was "there" in the session. Adding
`session.flush()` right after `session.add(item)` fixed it deterministically.
`test_repository.py`'s helper avoids this entirely by calling `session.commit()` inside
`_make_item()`, which flushes/commits before `create_config()` is ever called.

## Self-review (as requested)

- **Migration inverses correct**: `upgrade()` creates `items`, drops+recreates `configs.item_id` as `NOT NULL FK ondelete=CASCADE`; `downgrade()` drops+recreates `configs.item_id` as nullable, then drops `items` — verified this is a true inverse by running both directions against Postgres (see below), both exit 0.
- **`item_id` genuinely cannot be null** — verified directly (not just via the test suite):
  ```
  OK: null item_id rejected -> IntegrityError
  ```
  (constructed a `Config(item_id=None)` against a live SQLite session post-`init_db()` and confirmed `IntegrityError`.)
- **SQLite FK pragma is actually active, and cascade fires** — verified directly:
  ```
  OK: cascade delete removed the dependent config
  ```
  (created an `Item` + a `Config` pointing at it, deleted the `Item`, and confirmed both the `Item` and the dependent `Config` are gone — this proves both that FK enforcement is on and that `ON DELETE CASCADE` is honored by SQLite, which silently ignores both without the pragma.)
- **`uv run pytest` output is NOT pristine at the whole-repo level** — see Concerns below. It is pristine for every test file Task 1 is scoped to touch: `test_items_models.py` (2/2), `test_repository.py` (11/11), `test_configs_models.py` (2/2), plus all previously-passing files outside `configs`/`routes` (audit, tenants, users, auth, geonode, schemas, main_wiring — all still green).

## Concerns

**`test_routes.py` has 14 failing tests** (all `IntegrityError: FOREIGN KEY constraint failed` on the `configs` insert). Root cause: `POST /configs` (`app/configs/routes.py::create_config`) still creates the linked "item" via `app.geonode.StubItemClient.create_item()`, which only generates a random id (`"item-" + uuid4().hex`) — it never inserts a row into the new `items` table. Once FK enforcement is on and `item_id` is a real FK, every `INSERT INTO configs` done through the live HTTP route now fails, because no `items` row exists for that id.

I read the full SP-1b plan (`docs/superpowers/plans/2026-07-05-sp1b-items.md`) to check
whether this was anticipated. **It is, explicitly, but assigned to Task 3**, not Task 1:
Task 3 ("Wire item creation/deletion into `configs`; remove GeoNode from the create/delete
paths") rewrites `app/configs/routes.py` to call `items_repo.create_item(...)` instead of
`StubItemClient`, removes the `owner` field from `POST /configs`'s request body, and
replaces the affected tests in `test_routes.py` (different fixture, different assertions,
new `Item`-based checks) — Task 1's file list does not include `app/configs/routes.py` or
`test_routes.py` at all, and Task 1's brief never mentions either file.

This is a real fork, not a mechanical fix like Step 6's:
- **Option A (what I did)**: keep Task 1 strictly scoped to its stated file list; `test_routes.py` stays red until Task 2 (items repository/routes) and Task 3 (rewiring `configs/routes.py` to use it, removing GeoNode) land. This matches the plan's own stacked-task design exactly, and Task 3's diff for `test_routes.py`/`configs/routes.py` is already fully specified — duplicating any of it now in Task 1 would conflict with Task 3's explicit rewrite.
- **Option B**: pull forward a minimal chunk of Task 2/3's work now (make `create_config` insert a real `Item` row) to keep `uv run pytest` fully green — but this touches files outside Task 1's list and pre-empts Task 3's specified diff.

I chose Option A and did not touch `app/configs/routes.py` or `test_routes.py`, per the
brief's explicit "in over your head" instruction to stop and report rather than
guess/expand scope when FK enforcement causes unanticipated cross-cutting failures. If the
intent was instead for Task 1 alone to leave the whole suite green (e.g. by merging Task
2+3's relevant slice into this task), please advise — I did not want to unilaterally start
rewriting `app/configs/routes.py`, which the plan describes in full for Task 3.

**Test count**: 73 test functions collected (71 pre-existing + 2 new in `test_items_models.py`); 59 pass, 14 fail (all in `test_routes.py`).

## Postgres round-trip output

```
$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55441/gis uv run alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, items table; configs.item_id becomes a real FK
EXIT=0

$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55441/gis uv run alembic downgrade base
INFO  [alembic.runtime.migration] Running downgrade 0005 -> 0004, items table; configs.item_id becomes a real FK
... (all the way down to base)
EXIT=0
```

## Commit

`cf47042` — `feat(core): add items table; configs.item_id becomes a real cascading FK`
