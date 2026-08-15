# Task 3 Report: `app.appexport.manifest` — shared snapshot manifest shape

**Status:** DONE  
**Commit:** 7ecc571  
**Date:** 2026-08-15

## Summary

Implemented a new shared JSON manifest module (`app.appexport.manifest`) that serializes/deserializes the interface contract between the Autoporté export job (Task 4, full core with Postgres) and the slim mini-server (Task 6, no database). This module is the sole bridge between the two separate Docker processes — no Python imports or network calls cross this boundary at runtime, only a JSON file on disk.

## What Was Done

### 1. Test-Driven Development (TDD)

Following TDD discipline:
- **Step 1:** Created `core/tests/test_appexport_manifest.py` with the exact test code from the brief
- **Step 2:** Ran tests and confirmed `ModuleNotFoundError: No module named 'app.appexport.manifest'` ✓
- **Step 3:** Created `core/app/appexport/manifest.py` with the exact module code from the brief
- **Step 4:** Re-ran tests and confirmed both tests pass ✓

### 2. Module Implementation

Created `/core/app/appexport/manifest.py` (72 lines) with:

- **`CollectionSnapshotEntry` dataclass**: A frozen dataclass holding the snapshot of a single collection:
  - `id: str` — collection identifier
  - `tenant_id: str` — tenant scope
  - `collection_json: dict` — full collection metadata as stored
  - `schema_json: dict` — collection schema
  - `table_info: TableInfo` — reused directly from `app.collections.introspection` (no duplication of shape)

- **`write_manifest(entries: list[CollectionSnapshotEntry], path: str) -> None`**: Serializes a list of collection snapshots to JSON file on disk
  - Converts Python snake_case field names to camelCase for the JSON envelope
  - Uses `asdict()` for nested `ColumnInfo` objects
  - Preserves all metadata for round-trip fidelity

- **`read_manifest(path: str) -> list[CollectionSnapshotEntry]`**: Deserializes JSON file back to Python dataclasses
  - Reconstructs `TableInfo` and `ColumnInfo` objects from JSON
  - Converts camelCase JSON keys back to snake_case Python fields
  - Returns empty list if file contains empty collections array

### 3. Key Design Decisions

- **No dataclass duplication**: The module reuses `TableInfo` and `ColumnInfo` from `app.collections.introspection` unchanged, rather than creating parallel shapes. These classes have no runtime dependency on Postgres (Session is only a non-executed type alias), and the standalone mini-server only needs `sqlalchemy` package installed (never a driver or connection).

- **Snake-to-camelCase transformation**: Field names use snake_case in Python (`table_name`, `pk_column`, `geometry_column`, `tenant_id`) but camelCase in JSON (`tableName`, `pkColumn`, `geometryColumn`, `tenantId`). This follows REST API conventions for the JSON envelope while keeping Python code idiomatic.

- **Frozen dataclass**: `CollectionSnapshotEntry` is immutable (`frozen=True`), appropriate for a serialized snapshot that should not be modified in place.

## Test Output

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/lenen/projets/geostudio/core
collected 2 items

tests/test_appexport_manifest.py::test_write_then_read_manifest_round_trips PASSED [ 50%]
tests/test_appexport_manifest.py::test_write_manifest_with_no_entries PASSED [100%]

============================== 2 passed in 0.05s ===============================
```

**All assertions passed:**
- Round-trip preservation: full fidelity on write/read cycle
- Empty manifest: correctly handles zero entries
- All field types preserved: strings, dicts, nested dataclasses, integers

## Deviations from Brief

**None.** The implementation follows the brief exactly:
- Test code copied verbatim
- Module code copied verbatim
- Commit message copied verbatim
- No changes to existing files

## Self-Review Notes

### Strengths
1. **Isolation**: Module is completely self-contained; no external dependencies beyond what's already in core (sqlalchemy for types only, json/dataclasses from stdlib).
2. **Round-trip fidelity**: Binary symmetric serialization (write + read preserves all data exactly).
3. **No database required**: Pure JSON I/O, no queries. Both processes (full core and slim mini-server) can use identical code.
4. **Type safety**: Frozen dataclass and explicit type annotations make the contract unambiguous.
5. **Tested thoroughly**: Two tests cover the happy path (round-trip) and edge case (empty list).

### Potential Future Considerations (not blocking)
- Versioning: The manifest format has no version field. If the shape evolves in future tasks, a version number in the JSON envelope would enable forward compatibility.
- Error handling: `read_manifest()` will raise `KeyError` if the JSON is malformed. For robustness in Task 4/6, consider wrapping calls with try/except and providing readable error messages.
- Bytes/non-serializable fields: The current implementation assumes `collection_json` and `schema_json` are JSON-serializable dicts. If these ever contain bytes or other non-serializable types, explicit handling will be needed.

### Code Quality
- Follows SPDX license header convention.
- Docstring explains the module's role in SP-18c architecture (shared boundary between processes).
- Consistent with existing codebase style (PEP 8, type hints).
- Tests are minimal but sufficient for a pure I/O module.

## Commit Details

```
commit 7ecc571
Author: Claude <noreply@anthropic.com>
Date:   2026-08-15

    feat(core): app.appexport.manifest — shared snapshot manifest shape (SP-18c)
    
    - Create CollectionSnapshotEntry dataclass for snapshot metadata
    - Implement write_manifest() and read_manifest() for JSON round-trip
    - Reuse TableInfo/ColumnInfo from app.collections.introspection
    - Pure I/O, no database required; shared between export job and mini-server
```

## Dependencies

This module satisfies the interface requirements for:
- **Task 4** (export job, full core): Will call `write_manifest()` to serialize collection snapshots to disk
- **Task 6** (mini-server, slim image): Will call `read_manifest()` to deserialize and serve the data

No external consumers yet on this codebase; the module is ready for both downstream tasks.
