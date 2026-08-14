# Task 6 Report: Core read/proxy route

**Date:** 2026-08-14  
**Status:** DONE  
**Commit:** `d7c6bf6`

## Summary

Successfully implemented the authenticated read/proxy route `GET /tileset3d/{item_id}/{path:path}` that serves individual zip entries on demand via ranged S3 reads. This is the final core-side piece of the tileset3d hosting feature before OpenAPI regeneration. All tests passing, full suite green.

## Execution

### Step 1: Write Failing Tests
Appended 5 test cases to `core/tests/test_tileset3d_routes.py`:
- `test_read_tileset3d_entry_returns_tileset_json` — JSON extraction with correct content-type
- `test_read_tileset3d_entry_returns_tile_binary` — Binary extraction with octet-stream type
- `test_read_tileset3d_entry_404_for_missing_entry` — 404 for non-existent entry path
- `test_read_tileset3d_entry_404_for_unknown_item` — 404 for unknown item ID
- `test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user` — 404 for access denied

Also added helper functions:
- `_valid_zip_bytes()` — creates minimal tileset zip (tileset.json + tiles/0.b3dm)
- `_seed_hosted_tileset_item()` — seeds S3 fake, creates item, creates tileset3d config

### Step 2: Verify Tests Fail
Ran: `cd core && uv run pytest tests/test_tileset3d_routes.py -k read_tileset3d_entry -v`

Result:
```
FAILED test_read_tileset3d_entry_returns_tileset_json (404, expected 200)
FAILED test_read_tileset3d_entry_returns_tile_binary (404, expected 200)
PASSED test_read_tileset3d_entry_404_for_missing_entry
PASSED test_read_tileset3d_entry_404_for_unknown_item
PASSED test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user
```

✓ Expected failure: route doesn't exist yet, happy-path tests return 404 instead of 200

### Step 3: Implement the Route
Added to `core/app/tileset3d/routes.py`:
- Imports: `zipfile`, `Response`, `configs_repo`, `items_repo`, `can`, `S3RangeFile`
- Content type mapping `_CONTENT_TYPES` (7 file extensions)
- Helper `_content_type_for(path: str)` — guesses MIME type from extension
- Route handler `read_tileset3d_entry()`:
  - Authorization via `items_repo.get_access_facts()` + `can()` → 404 if denied
  - Config lookup via `configs_repo.get_config_by_item()` → 404 if missing
  - S3RangeFile for efficient byte-range reads
  - Zip entry extraction via `ZipFile.read(path)` → 404 if KeyError
  - Content-Type guessing via `_content_type_for(path)`
  - Cache-Control header: "private, max-age=3600"

### Step 4: Verify Tests Pass
Ran: `cd core && uv run pytest tests/test_tileset3d_routes.py -v`

Result:
```
12 passed in 3.88s
```

✓ All tests passing (7 existing + 5 new)

### Step 5: Run Full Suite
Ran: `cd core && uv run pytest -q`

Result:
```
1432 passed, 145 skipped in 99.36s
```

✓ Full suite green, no regressions

### Step 6: Commit
```bash
git add core/app/tileset3d/routes.py core/tests/test_tileset3d_routes.py
git commit -m "feat(core): tileset3d read/proxy route"
```

**Commit hash:** `d7c6bf6`  
**Staged files:** 2 (routes.py + test file)  
**Status output:**
```
[dev d7c6bf6] feat(core): tileset3d read/proxy route
 2 files changed, 132 insertions(+)
```

## Files Changed

1. **`core/app/tileset3d/routes.py`** (+64 lines)
   - Added imports: zipfile, Response, configs_repo, items_repo, can, S3RangeFile
   - Added `_CONTENT_TYPES` dict (extension → MIME type mapping)
   - Added `_content_type_for(path)` helper
   - Added `read_tileset3d_entry(item_id, path, ...)` route (GET /tileset3d/{item_id}/{path:path})

2. **`core/tests/test_tileset3d_routes.py`** (+68 lines)
   - Added imports: io, json, zipfile, BuilderConfig, Tileset3DPayload, configs_repo
   - Added `_valid_zip_bytes()` helper
   - Added `_seed_hosted_tileset_item()` helper
   - Added 5 test cases for read route (json, binary, missing entry, unknown item, auth denied)

## Technical Details

**Route Signature:**
```python
@router.get("/tileset3d/{item_id}/{path:path}")
def read_tileset3d_entry(
    item_id: str, path: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Response
```

**Authorization Logic:**
1. Fetch access facts via `items_repo.get_access_facts()`
2. Check `can(session, user_id, action="read", item=facts)`
3. Return 404 if facts is None or authorization fails (hiding item existence)

**Content Delivery Logic:**
1. Get tileset3d config via `configs_repo.get_config_by_item()`
2. Return 404 if config missing or not tileset3d kind
3. Create `S3RangeFile` for byte-range reads
4. Open zip and extract entry via `ZipFile.read(path)`
5. Return 404 if entry not found (KeyError)
6. Return Response with guessed content-type and cache header

**Content-Type Mapping:**
- `.json` / `.gltf` → `application/json`
- `.b3dm` / `.i3dm` / `.pnts` / `.cmpt` / `.glb` → `application/octet-stream`
- Default → `application/octet-stream`

## Quality Checks

✓ All 5 new read tests passing  
✓ All 7 existing tileset3d tests still passing  
✓ Full test suite green (1432 passed)  
✓ Authorization properly enforced (can() check)  
✓ Config validation (kind="tileset3d")  
✓ Proper 404 handling for 3 error cases (item, config, entry)  
✓ Content-Type guessing extensible (new extensions easily added)  
✓ S3RangeFile correctly used for efficient ranged reads  
✓ Scope discipline: only 2 files changed (routes + test)  
✓ Code follows brief exactly (no deviations)

## Integration Notes

This route completes the core-side tileset3d hosting feature. Ready for:
- **Task 7**: OpenAPI spec regeneration (spec will now include this new route)
- **Task 8-13**: Shell integration (types, itemClient, layer picker, map view, upload UI, E2E)

The route integrates cleanly with existing dependency injection patterns and follows authorization conventions established in `app.sharing`.

## Concerns

None. Route is complete as specified, all tests pass, ready for downstream tasks.
