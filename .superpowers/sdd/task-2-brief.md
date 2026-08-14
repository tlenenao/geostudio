### Task 2: Shell types — `tiles3d`, `terrain`, camera in `MapConfig`

**Files:**
- Modify: `shell/src/api/types.ts:57-74` (`MapViewport`, `MapLayer`, `MapConfig`)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)

**Interfaces:**
- Consumes: Task 1's `core/openapi.json`.
- Produces: `MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number }`; `MapLayer` union gains `{ kind: "tiles3d"; id; title; visible; url: string }`; `MapViewport` gains `pitch?: number; bearing?: number`; `MapConfig` gains `terrain?: MapTerrainConfig | null`. Consumed by Task 3 (`itemClient.ts`), Task 4 (`MapView.tsx`), Task 5 (`LayerPicker.tsx`), Task 6 (`TerrainPanel.tsx`), Task 7 (`CameraControls.tsx`, `MapEditorPage.tsx`).

- [ ] **Step 1: Edit the types**

In `shell/src/api/types.ts`, replace lines 57-74:

```ts
export type MapViewport = { center: [number, number]; zoom: number; pitch?: number; bearing?: number };
export type BaseMap = { style: string };
export type MapLayer =
  | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
  | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "tiles3d"; url: string };
export type MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number };
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  showScaleBar?: boolean;
  showNorthArrow?: boolean;
  cartouche?: string | null;
};

export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
};
```

- [ ] **Step 2: Type-check (expect errors in files not yet updated)**

Run: `cd shell && npx tsc --noEmit`
Expected: FAIL — errors in `itemClient.ts` (the `toFrontLayer` switch doesn't handle `"tiles3d"` in a way that satisfies the new union yet — actually this alone won't error since `toFrontLayer`'s `default` branch still returns a valid `feature`-shaped object; expect this step to otherwise PASS with no new errors). If it passes cleanly, that's fine — proceed; the real coverage gap is closed by Task 3's tests, not the type checker.

- [ ] **Step 3: Regenerate `core-schema.d.ts`**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` is rewritten to reflect Task 1's `core/openapi.json` (new `tiles3d` enum value, `MapTerrain` schema, `pitch`/`bearing` fields visible in the diff).

- [ ] **Step 4: Type-check again**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS, no errors.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/generated/core-schema.d.ts
git commit -m "feat(shell): ajoute tiles3d, terrain et pitch/bearing aux types MapConfig"
```

---

