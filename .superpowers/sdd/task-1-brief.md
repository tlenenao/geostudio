### Task 1: Core schema — `tiles3d` layer kind, `terrain`, camera pitch/bearing

**Files:**
- Modify: `core/app/configs/schemas.py:61-88` (`MapView`, `MapLayer`, `MapConfig` classes)
- Test: `core/tests/test_routes.py`

**Interfaces:**
- Produces: `MapLayer.kind` Literal including `"tiles3d"` (reuses existing `url: str | None` field, no new field); `MapTerrain(tilesUrl: str, encoding: Literal["terrarium"] = "terrarium", exaggeration: float | None = None)`; `MapConfig.terrain: MapTerrain | None = None`; `MapView.pitch: float | None = None`, `MapView.bearing: float | None = None`. These exact JSON field names are consumed by shell Task 2/3 (`MapLayer`/`MapConfig`/`MapViewport` TS types and `itemClient.ts` wire mapping).

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_routes.py` (near the existing `_map_config`/`test_map_config_*` tests, e.g. after `test_put_config_by_item_404_when_missing`):

```python
def test_map_config_round_trips_tiles3d_layer_terrain_and_camera(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte 3D",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [2.35, 48.85], "zoom": 5, "pitch": 45, "bearing": 90},
                    "layers": [
                        {"id": "bldg", "title": "Bâtiments", "visible": True,
                         "kind": "tiles3d", "url": "https://example.test/tileset.json"},
                    ],
                    "terrain": {
                        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
                        "encoding": "terrarium",
                        "exaggeration": 1.5,
                    },
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]["map"]
    assert body["view"]["pitch"] == 45
    assert body["view"]["bearing"] == 90
    assert body["layers"][0] == {
        "id": "bldg", "title": "Bâtiments", "visible": True, "kind": "tiles3d",
        "tilesUrl": None, "sourceLayer": None, "url": "https://example.test/tileset.json",
        "opacity": None, "deckType": None, "dataUrl": None, "paint": None, "props": None,
    }
    assert body["terrain"] == {
        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
        "encoding": "terrarium",
        "exaggeration": 1.5,
    }


def test_map_config_defaults_pitch_bearing_terrain_when_absent(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte plate",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [0, 0], "zoom": 1},
                    "layers": [],
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]
    body = client.get(f"/configs/by-item/{item_id}").json()["config"]["map"]
    assert body["view"]["pitch"] is None
    assert body["view"]["bearing"] is None
    assert body["terrain"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_routes.py -k "tiles3d_layer_terrain_and_camera or defaults_pitch_bearing_terrain" -v`
Expected: FAIL — `tiles3d` rejected as an invalid `kind` (Pydantic validation error, response not 201), and `terrain`/`pitch`/`bearing` unrecognized/absent from the response body.

- [ ] **Step 3: Implement the schema changes**

In `core/app/configs/schemas.py`, replace the `MapView`, `MapLayer`, `MapConfig` classes (currently lines 61-88):

```python
class MapView(BaseModel):
    center: tuple[float, float]
    zoom: float
    pitch: float | None = None
    bearing: float | None = None


class BaseMap(BaseModel):
    style: str


class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck", "tiles3d"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None


class MapTerrain(BaseModel):
    tilesUrl: str
    encoding: Literal["terrarium"] = "terrarium"
    exaggeration: float | None = None


class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)
    terrain: MapTerrain | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_routes.py -k "tiles3d_layer_terrain_and_camera or defaults_pitch_bearing_terrain" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full core suite for regressions**

Run: `cd core && uv run pytest -q`
Expected: all passing, same count as before plus the 2 new tests (no existing map-config test broken — `pitch`/`bearing`/`terrain` are all optional/defaulted).

- [ ] **Step 6: Regenerate `openapi.json`**

Run:
```bash
cd core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
```
Expected: `core/openapi.json` is rewritten; `git diff --stat core/openapi.json` shows changes reflecting the new `tiles3d` enum value, `MapTerrain` schema, and `pitch`/`bearing` fields.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_routes.py core/openapi.json
git commit -m "feat(core): ajoute le kind tiles3d, le terrain et pitch/bearing à MapConfig"
```

---

