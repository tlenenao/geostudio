# Task 5 report — Per-node validation (`app.pipelines` layer)

## Commit

- `fe82563` — `feat(core): validate pipeline node params + collection permissions at save time`
  - `core/app/pipelines/config_validation.py` (new)
  - `core/app/main.py` (modified: side-effect import added right after the
    `harvest_dataset_validation` import, before `collections_routes`)
  - `core/tests/test_pipeline_node_validation.py` (new)

## Signature check (before writing code)

Confirmed against the live codebase, all three matched the brief verbatim —
no adjustment needed to `config_validation.py` itself:

- `app.collections.repository.get_collection(session, *, tenant_id, collection_id) -> Collection | None`
- `app.collections.repository.get_access_facts(col: Collection) -> AccessFacts`
- `app.sharing.authorization.can(session, *, user_id, action, item, kind="item", actor_is_admin=False) -> bool`
- `app.pipelines.ops.schemas.OP_PARAMS: dict[str, type[BaseModel]]` and its
  `ReaderCollectionParams.collectionId` / `TransformJoinParams.withCollectionId`
  / `WriterCollectionParams.collectionId` field names — all match
  `_COLLECTION_PARAM_FIELD`.
- `app.configs.schemas.PipelineNode` — `id`, `kind`, `op`, `params: dict`.
- `app.users.models.User` — has `tenant_id`, `id`, `is_admin`.
- `app.configs.pipeline_validation.register_pipeline_node_validator(op, validator)`
  exists exactly as Task 4 left it.

## One real discrepancy found (test fixture, not the three signatures above)

The brief's `test_pipeline_node_validation.py` fixture inserts fixture rows
into `collections` via raw SQL (`INSERT INTO collections (...) VALUES (...)`)
without `created_at`/`updated_at`. `Collection.created_at`/`updated_at`
(`core/app/collections/models.py`) use a **Python-side** default
(`default=_now`, applied by the ORM on `session.add()`), not a SQL-level
`DEFAULT` — so a raw-SQL insert bypassing the ORM hits SQLite's `NOT NULL`
constraint on `created_at`.

This was not one of the three signatures I was told to check in advance, so
I did not stop and ask — it's a mechanical test-fixture gap (the brief's raw
`INSERT` simply omits two required columns), not an ambiguity in business
logic or in `get_collection`/`get_access_facts`/`can()`. I fixed it by
adding `created_at, updated_at` columns with `CURRENT_TIMESTAMP` values to
all three `INSERT` statements in the fixture. Nothing in
`config_validation.py` or `main.py` needed to change — the implementation
code is exactly as given in the brief.

## TDD steps followed

1. Wrote `core/tests/test_pipeline_node_validation.py` per the brief.
2. Ran it — hit the `created_at` NOT NULL error described above (fixture
   bug, not the predicted failure). Fixed the fixture, re-ran:
   `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
   → 2 failed / 3 passed, with the exact failure mode the brief predicted:
   `test_valid_pipeline_with_existing_collections_saves` got 422, and
   `test_reader_collection_missing_is_rejected` got
   `"unknown op 'reader.collection'"` instead of a collection-not-found
   message (no real validator registered yet). Matches the brief's
   "Expected: FAIL" step exactly once the fixture bug was out of the way.
3. Implemented `core/app/pipelines/config_validation.py` verbatim from the
   brief (Step 3).
4. Wired the side-effect import into `core/app/main.py` verbatim (Step 4).
5. Re-ran: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
   → **5 passed**.
6. Regression check:
   `cd core && uv run pytest tests/test_pipeline_config_validation.py tests/test_pipeline_config_schema.py tests/test_pipeline_ops_schemas.py tests/test_configs_extension_permissions.py -v`
   → **34 passed**, no change in behaviour.
7. Full suite as an extra safety net (not required by the brief, ran anyway
   given the fixture surprise): `cd core && uv run pytest -q`
   → **924 passed, 114 skipped** (skipped = postgis-marked tests needing
   docker, pre-existing and unrelated).
8. Committed exactly the three files the brief named:
   `git add core/app/pipelines/config_validation.py core/app/main.py core/tests/test_pipeline_node_validation.py`
   then the exact commit message from the brief. Other unrelated
   uncommitted changes already present in the working tree
   (`.superpowers/sdd/*` progress files from prior tasks, two new docs under
   `docs/superpowers/`) were left untouched, as instructed.

## Concerns

- None on the implementation itself — it is a byte-for-byte transcription
  of the brief's `config_validation.py`, and every signature it depends on
  was verified against the live code before writing it.
- The only note-worthy thing is the test-fixture `created_at`/`updated_at`
  gap described above. It's a one-line-per-statement fix with no semantic
  ambiguity, so I did not treat it as a "brief vs. codebase" blocker
  requiring a stop-and-ask, but flagging it here in case a later task's
  brief reuses this same raw-SQL-into-`collections` pattern and needs the
  same fix.
- Note: this file previously contained a stale report from an unrelated
  earlier task (SP-14n, shell-side `bboxFromGeometry`/`derivePatch`) that
  happened to reuse the same generic filename `task-5-report.md`. That
  content has been fully replaced by this report; it is unrelated to the
  work described here and its content (commit `4debf7d`) is untouched on
  disk/in git history.
