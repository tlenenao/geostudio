# Builder Service Map Kind (SP-0c-a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Builder Service store and validate map items — extend `BuilderConfig` with `kind="map"` and a `MapConfig` payload (basemap + view + layers) — so the front can create/save maps through the existing `/configs` endpoints.

**Architecture:** Additive change to the SP-0a FastAPI Builder Service. `BuilderConfig.kind` gains `"map"`; `layout` becomes optional; a new `map: MapConfig | None` field holds the map payload. A model validator enforces "app/dashboard require `layout`; map requires `map`", so existing app/dashboard behavior is unchanged. The existing generic routes (`POST/GET/PUT /configs`, by-item) then round-trip a map config with no route code change.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, uv.

## Global Constraints

- Work under `builder-service/`; run `uv run pytest` from there; keep output pristine (`filterwarnings = ["error", ...]`).
- Additive only: the app/dashboard contract (`ConfigRead`, `POST/GET/PUT /configs`, revisions, rollback, by-item, `ItemClient`) must not change behavior.
- A `map` config validates with `kind="map"` + a `map` object and no `layout`; an `app`/`dashboard` config still requires `layout`.
- The `MapConfig` shape (façade source of truth): `{ basemap: { style }, view: { center: [lng,lat], zoom }, layers: MapLayer[] }`; `MapLayer` has `id`, `title`, `visible`, `kind` ∈ `vector|raster|feature|deck`, plus kind-specific optional fields (`tilesUrl`, `sourceLayer`, `url`, `opacity`, `deckType`, `dataUrl`, `paint`, `props`).
- Stage only the files each task lists (explicit paths); never stage `__pycache__`.

---

### Task 1: `MapConfig` schema + `BuilderConfig` extension

**Files:**
- Modify: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py` (add cases)

**Interfaces:**
- Produces in `app.schemas`:
  - `MapView(center: tuple[float, float], zoom: float)`.
  - `BaseMap(style: str)`.
  - `MapLayer(id, title, visible=True, kind: Literal["vector","raster","feature","deck"], tilesUrl=None, sourceLayer=None, url=None, opacity=None, deckType=None, dataUrl=None, paint=None, props=None)`.
  - `MapConfig(basemap: BaseMap, view: MapView, layers: list[MapLayer] = [])`.
  - `BuilderConfig` changed: `kind: Literal["app","dashboard","map"]`, `layout: Layout | None = None`, `map: MapConfig | None = None`, plus a `model_validator(mode="after")` requiring `layout` for app/dashboard and `map` for map.

- [ ] **Step 1: Write the failing tests**

Add to `builder-service/tests/test_schemas.py`:

```python
def _valid_map_payload() -> dict:
    return {
        "version": 1,
        "kind": "map",
        "map": {
            "basemap": {"style": "https://demotiles.maplibre.org/style.json"},
            "view": {"center": [2.35, 48.85], "zoom": 5},
            "layers": [
                {"id": "l1", "title": "Communes", "visible": True,
                 "kind": "vector", "tilesUrl": "https://martin/communes/{z}/{x}/{y}",
                 "sourceLayer": "communes"},
            ],
        },
    }


def test_valid_map_config_parses():
    from app.schemas import BuilderConfig

    config = BuilderConfig.model_validate(_valid_map_payload())
    assert config.kind == "map"
    assert config.layout is None
    assert config.map is not None
    assert config.map.layers[0].kind == "vector"
    assert config.map.view.center == (2.35, 48.85)


def test_map_config_requires_map_field():
    import pytest
    from pydantic import ValidationError
    from app.schemas import BuilderConfig

    payload = _valid_map_payload()
    del payload["map"]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_app_config_still_requires_layout():
    import pytest
    from pydantic import ValidationError
    from app.schemas import BuilderConfig

    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"kind": "app"})
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_schemas.py -k "map or layout" -v`
Expected: FAIL — `map`/`kind="map"` not accepted; validator absent.

- [ ] **Step 3: Update `builder-service/app/schemas.py`**

Add the imports at the top (extend the existing pydantic import):

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
```

Add the map models (near the other models, before `BuilderConfig`):

```python
class MapView(BaseModel):
    center: tuple[float, float]
    zoom: float


class BaseMap(BaseModel):
    style: str


class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None


class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)
```

Replace the `BuilderConfig` class with:

```python
class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout | None = None
    messages: list[Message] = Field(default_factory=list)
    map: MapConfig | None = None

    @model_validator(mode="after")
    def _require_kind_payload(self) -> "BuilderConfig":
        if self.kind in ("app", "dashboard") and self.layout is None:
            raise ValueError(f"{self.kind} config requires a layout")
        if self.kind == "map" and self.map is None:
            raise ValueError("map config requires a map")
        return self
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS (existing + 3 new). The existing `test_layout_required` still passes (validator rejects an app without layout).

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/schemas.py builder-service/tests/test_schemas.py
git commit -m "feat(builder-service): add map kind + MapConfig to BuilderConfig"
```

---

### Task 2: Map config round-trips through the config routes

**Files:**
- Test: `builder-service/tests/test_routes.py` (add a case)

**Interfaces:**
- Consumes: the existing `client` fixture + `_create`/route helpers; the extended `BuilderConfig` (Task 1). No route code change — this task proves the generic routes accept and round-trip a map config.

- [ ] **Step 1: Write the failing test**

Add to `builder-service/tests/test_routes.py`:

```python
def _map_config() -> dict:
    return {
        "kind": "map",
        "map": {
            "basemap": {"style": "https://demotiles.maplibre.org/style.json"},
            "view": {"center": [2.35, 48.85], "zoom": 5},
            "layers": [
                {"id": "l1", "title": "Communes", "visible": True,
                 "kind": "vector", "tilesUrl": "https://martin/communes/{z}/{x}/{y}",
                 "sourceLayer": "communes"},
            ],
        },
    }


def test_map_config_round_trips_through_create_and_get(client):
    response = client.post(
        "/configs",
        json={"title": "Ma carte", "owner": "alice", "config": _map_config()},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["kind"] == "map"

    fetched = client.get(f"/configs/{created['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["config"]["kind"] == "map"
    assert body["config"]["map"]["layers"][0]["sourceLayer"] == "communes"

    # by-item GET (used by the front's getMapConfig) also returns the map
    item_id = created["itemId"]
    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    assert by_item.json()["config"]["map"]["view"]["zoom"] == 5


def test_map_config_can_be_updated(client):
    created = client.post(
        "/configs",
        json={"title": "Ma carte", "owner": "alice", "config": _map_config()},
    ).json()
    updated = _map_config()
    updated["map"]["view"]["zoom"] = 9
    response = client.put(f"/configs/{created['id']}", json=updated)
    assert response.status_code == 200
    assert response.json()["config"]["map"]["view"]["zoom"] == 9
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_routes.py -k map -v`
Expected: FAIL before Task 1 is present; with Task 1 done it should PASS — run it to confirm the routes accept the map config. If it FAILS on a schema/validation error, fix Task 1; if it passes, the routes need no change.

- [ ] **Step 3: Confirm (no route change expected)**

The routes serialize/deserialize `BuilderConfig` generically, so no code change is needed. If the test passes, proceed. If `ConfigRead`/response serialization drops the `map` field, ensure `ConfigRead.config` is typed as `BuilderConfig` (it is) so the `map` field serializes.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run pytest -q`
Expected: PASS, pristine.

- [ ] **Step 5: Commit**

```bash
git add builder-service/tests/test_routes.py
git commit -m "test(builder-service): map config round-trips through config routes"
```

---

## Self-Review

**Spec coverage (against SP-0c §3 Builder Service extension + phase 0c-a):**
- `kind="map"`, `layout` optional, `map` field, validator → Task 1. ✅
- `MapConfig`/`MapView`/`BaseMap`/`MapLayer` models → Task 1. ✅
- Map config round-trips through `POST/GET/PUT /configs` + by-item (used by `getMapConfig`/`saveMapConfig`) → Task 2. ✅
- Existing app/dashboard contract unchanged (validator preserves `layout` requirement) → Task 1. ✅

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `MapConfig` (Task 1) is the payload the Task 2 tests build and round-trip. `BuilderConfig.map: MapConfig | None` (Task 1) flows through `ConfigRead.config` unchanged. The by-item GET route (from SP-0b.2-c) returns the same `ConfigRead`. ✅

## Notes for SP-0c-b..e

- The front `getMapConfig(pk)` = `GET /configs/by-item/{pk}` → `config.map`; `saveMapConfig` = `PUT /configs/{id}` with `{ kind: "map", map }`; `createMapItem` = `POST /configs` with a skeleton map config.
- `MapView` (0c-b) translates `config.map` into MapLibre sources/layers; Deck.gl overlay (0c-c) for `kind: "deck"` layers.
