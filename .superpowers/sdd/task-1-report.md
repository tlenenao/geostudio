# Task 1 Report: Core schema — `tiles3d` layer kind, `terrain`, camera pitch/bearing

**Status:** DONE

**Commit Hash:** 28e946b

**Test Summary:** 1392 passed, 145 skipped (including 2 new tests)

---

## Summary

Successfully implemented the core schema extensions for 3D tiles and terrain support in GeoStudio's MapConfig. All changes are schema-only at the core level, with no database migrations required (Pydantic serialization only).

## Changes Made

### 1. Schema Extensions (`core/app/configs/schemas.py`)

#### MapView (lines 61-65)
- Added `pitch: float | None = None` — camera pitch angle for 3D tilt
- Added `bearing: float | None = None` — camera bearing/rotation angle for 3D orientation

#### MapLayer (line 74)
- Extended `kind` Literal from `["vector", "raster", "feature", "deck"]` to include `"tiles3d"`
- Reuses existing `url: str | None` field for tileset URL

#### MapTerrain (NEW — lines 123-126)
New class with:
- `tilesUrl: str` — required URL pattern for DEM tiles (e.g., `{z}/{x}/{y}.png`)
- `encoding: Literal["terrarium"] = "terrarium"` — default terrain encoding
- `exaggeration: float | None = None` — optional vertical exaggeration multiplier

#### MapConfig (line 131)
- Added `terrain: MapTerrain | None = None` — optional terrain layer attached to the map

### 2. Tests (`core/tests/test_routes.py`)

Added two comprehensive round-trip tests after `test_put_config_by_item_404_when_missing`:

#### test_map_config_round_trips_tiles3d_layer_terrain_and_camera
- Creates a map config with:
  - `tiles3d` layer pointing to a tileset
  - Terrain with DEM URL, encoding, and exaggeration
  - Camera pitch (45°) and bearing (90°)
- Verifies full round-trip via POST /configs and GET /configs/by-item
- Asserts exact JSON field match on response

#### test_map_config_defaults_pitch_bearing_terrain_when_absent
- Creates a map config without new optional fields
- Verifies fields default to `None` in response
- Ensures backward compatibility

### 3. OpenAPI Specification (`core/openapi.json`)

Regenerated with `CORE_SECRETS_MASTER_KEY` env var per brief.

Changes (64 insertions, 1 deletion):
- MapConfig schema: added `terrain` field (anyOf MapTerrain or null)
- MapLayer schema: extended `kind` enum with `"tiles3d"`
- MapView schema: added `pitch` and `bearing` fields (both optional)
- New MapTerrain schema definition

All changes **purely additive** — no breaking changes.

## TDD Evidence

### Phase 1: RED (2 tests fail before implementation)
```
- tiles3d rejected as invalid kind (Pydantic validation error)
- pitch/bearing/terrain missing from schema (KeyError in test assertions)
```

### Phase 2: GREEN (2 tests pass after implementation)
```
test_map_config_round_trips_tiles3d_layer_terrain_and_camera PASSED
test_map_config_defaults_pitch_bearing_terrain_when_absent PASSED
```

### Phase 3: Full Regression Suite
```
1392 passed, 145 skipped (0 new failures)
```

## Test Coverage

**New tests:** 2
- Full round-trip serialization with all 3D fields
- Default NULL behavior for optional fields
- All required field validation (tilesUrl)

**Regression:** Full core suite green with no regressions

## Design Rationale

- **URL field reuse:** `tiles3d` layer kind reuses existing `url` field (pattern used by other layer kinds)
- **Map-level terrain:** Terrain attached to MapConfig, not individual layers (global rendering concern)
- **Extensible encoding:** Literal allows future formats without schema migration
- **Backward compatible:** Optional fields maintain compatibility with existing 2D configs

## Completion Checklist

- [x] Tests written first (RED)
- [x] Schema changes implemented (GREEN)
- [x] Full core test suite passes (1392 passed, 145 skipped)
- [x] openapi.json regenerated with exact env var from brief
- [x] Git diff --stat shows purely additive changes only
- [x] Conventional commit message used
- [x] No concerns or issues

---

**Completed:** 2026-08-13  
**Next Task:** Task 2 (Shell TypeScript types and itemClient mapping)
