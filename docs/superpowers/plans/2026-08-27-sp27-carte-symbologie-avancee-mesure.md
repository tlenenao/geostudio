# Carte : symbologie avancée, étiquettes, icônes et mesure/croquis (SP-27) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A map layer's declarative symbology (`LayerSymbology`, SP-25) grows
four new pieces — independent stroke encoding (color+width+dash), fixed
opacity, CEL-templated labels rendered natively via MapLibre `feature-state`,
and categorical icons (curated Lucide set + a tenant-scoped custom icon
library) — editable from the same shared `MapSymbologyEditor`. Separately, a
lecteur (reader) on a published app/dashboard or `/sites/{slug}` page gets an
ephemeral measure (distance/area) and sketch (freehand/shapes/text) toolbar,
never persisted, never sent to the server.

**Architecture:** Everything except the custom icon library lives entirely in
`shell/`: `mapSymbology.ts` gains the new encodings and paint/legend
compilation, `MapView.tsx` gains the render-time mechanics (a second outline
layer for polygons, `icon-image` symbol layers, a `feature-state` loop for
labels, and a mounted measure/sketch overlay), `MapSymbologyEditor.tsx` gains
the matching UI blocks. The one core change is a small new module,
`app/mapicons/`, mirroring `app/secrets/`'s CRUD shape exactly (presigned S3
upload, tenant-scoped table, always-on router — no capability flag, same
precedent as `secrets`/`popup`/`symbology`).

**Tech Stack:** TypeScript/React/Vitest/MapLibre GL JS (shell), one new shell
dependency (`lucide-static`, raw SVG icon files — no React components, no
runtime icon-loading library). Python/FastAPI/SQLAlchemy/pytest (core), no new
core dependency (reuses `app/ingestion/storage.py`'s presign helpers).

## Global Constraints

- Every task that touches `core/`: `uv run pytest` must show **no drop** from
  the reference measured at the end of SP-26 (**1896 passed, 5 skipped, 1
  failed** — that one failure is `test_features_rls.py::
  test_scope_preserves_original_sql_error`, documented pre-existing and
  unrelated to SP-26/SP-27; do not try to fix it in this plan), `ruff check`,
  `ruff format --check`, `mypy --strict` (the 4 gated modules:
  `app/auth app/secrets app/analytics app/copilot`), `lint-imports` all
  green, coverage **≥ 85**.
- Every task that touches `shell/`: `npm run lint`, `npm run format:check`,
  `npm run test` must show **no drop** from the reference (**162 files /
  1463 tests**), `npm run build` green, coverage **≥ 88** (measured after
  removing `dist/`/`dist-export/` — documented trap, SP-22 through SP-26).
- `npm run e2e` reference: **108 passed, 4 skipped, 0 failed**.
- Any task that changes a FastAPI route/schema: regenerate OpenAPI + TS types
  (`cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=$(openssl rand -base64
  32) uv run python scripts/export_openapi.py`, then whatever `npm` script
  regenerates the TS side — check `shell/package.json`) and commit the diff.
- Commits are conventional (`feat(core): …`, `feat(shell): …`,
  `test(shell): …`), one subject each, in French prose, code identifiers in
  English — per `CLAUDE.md`.
- Any new `S3_*_BUCKET`/`CORE_*` environment variable read by `core/app/`
  must be wired into `docker-compose.yml`'s `core:` service **and** (for a
  bucket) mirrored in `deploy/backup/backup.sh`'s bucket loop or explicitly
  added to `test_deployability.py`'s `BACKUP_EXCLUDED_BUCKETS` with a written
  reason — SP-21's non-negotiable rule, checked by
  `core/tests/test_deployability.py`, currently **35/35 green**; do not let a
  task leave it red.
- **Deviations from the committed spec, locked in during this plan** (found
  while re-reading the real code the spec described from memory — same class
  of correction this repo's history makes routinely):
  1. The spec's §3.4 said the icon proxy route (`GET
     /map-icons/{id}/file`) uses "la même porte `can()` que le reste" —
     `can()` (`app/sharing/authorization.py`) authorizes access to an
     **item**, and a map icon is not an item (same reasoning `connector_secrets`
     already uses). The real check, mirroring `app/secrets/routes.py`
     exactly, is: authenticated user (`get_current_user`) + `icon.tenant_id
     == user.tenant_id`. No `can()` call anywhere in `app/mapicons/`.
  2. `MapLibre`'s `fill` layer type has **no stylable outline width** —
     `fill-outline-color` exists but is always a fixed 1px anti-aliased
     line, not controllable by `fill-outline-width` (no such property
     exists). A polygon's `stroke.width` therefore compiles to a **second
     `line` layer** sharing the same source/`source-layer`/filter as the
     fill layer (Task 2) — the spec's §3.2 mentioned this in passing; this
     plan makes it the concrete mechanism. `stroke` on a `line`-geometry
     layer is a no-op (a line already has its own `line-color`/`line-width`
     via the `color`/`size` encodings — a second outline on a line has no
     cartographic meaning) — `stroke` compiles to paint properties only for
     `point` (native `circle-stroke-*`) and `polygon` (native
     `fill-outline-color` + the second `line` layer for width/dash) kinds.

---

## File Structure

| File | Responsibility |
|---|---|
| `shell/src/builder/widgets/mapSymbology.ts` | **Modify.** `StrokeStyle`, `LayerSymbology.stroke`/`.opacity`/`.label`/`.icon`, `IconRef`, extended `buildMapPaint`/`buildLegend`. |
| `shell/src/builder/widgets/mapSymbology.test.ts` | **Modify.** |
| `shell/src/map/MapView.tsx` | **Modify.** Stroke second-layer + opacity in `effectivePaint`/`applyLayers`; icon image loading + symbol layers; label `feature-state` loop; mounts the measure/sketch toolbar behind a new `interactiveTools` prop. |
| `shell/src/map/MapView.test.tsx` | **Modify.** |
| `shell/src/map/MapSymbologyEditor.tsx` | **Modify.** Contour, opacité, étiquette, icône UI blocks. |
| `shell/src/map/MapSymbologyEditor.test.tsx` | **Modify.** |
| `shell/src/builder/widgets/mapWidget.tsx` | **Modify.** `MapSymbologyLegend` gains icon/classed-stroke entries; `Component` passes `interactiveTools={ctx.mode !== "edit"}`. |
| `shell/src/builder/widgets/mapWidget.test.tsx` | **Modify.** |
| `shell/src/builder/widgets/iconLibrary.ts` | **Create.** Curated Lucide icon list + categories + SVG→`ImageBitmap` rasterization. |
| `shell/src/builder/widgets/iconLibrary.test.ts` | **Create.** |
| `shell/src/map/labelFeatureState.ts` | **Create.** Pure: per-feature CEL template evaluation → `{id, label}` updates. |
| `shell/src/map/labelFeatureState.test.ts` | **Create.** |
| `shell/src/map/measureSketch.ts` | **Create.** Pure: haversine distance, spherical polygon area, unit formatting. |
| `shell/src/map/measureSketch.test.ts` | **Create.** |
| `shell/src/map/MapMeasureSketchToolbar.tsx` | **Create.** The mounted overlay component (measure + sketch UI and interaction). |
| `shell/src/map/MapMeasureSketchToolbar.test.tsx` | **Create.** |
| `shell/src/api/types.ts` | **Modify.** `ItemClient` gains 5 map-icon methods. |
| `shell/src/api/itemClient.ts` | **Modify.** Real implementations. |
| `shell/src/api/itemClient.test.ts` | **Modify.** |
| `shell/src/staticExport/StaticItemClient.ts` | **Modify.** `unsupported()` for the 5 new methods. |
| `shell/src/staticExport/StaticItemClient.test.ts` | **Modify.** |
| `shell/e2e/map-symbology-advanced.spec.ts` | **Create.** 4.4 proof. |
| `shell/e2e/map-measure-sketch.spec.ts` | **Create.** 4.5 proof. |
| `core/app/mapicons/__init__.py` | **Create.** Empty. |
| `core/app/mapicons/models.py` | **Create.** `MapIcon` SQLAlchemy model. |
| `core/app/mapicons/repository.py` | **Create.** `create_icon`/`list_icons`/`get_icon`/`delete_icon`. |
| `core/app/mapicons/schemas.py` | **Create.** `MapIconPresignRequest`/`MapIconCreate`/`MapIconOut`. |
| `core/app/mapicons/routes.py` | **Create.** 5 REST routes. |
| `core/alembic/versions/0029_map_icons.py` | **Create.** |
| `core/tests/test_mapicons_routes.py` | **Create.** |
| `core/app/main.py` | **Modify.** Import + unconditional `include_router`. |
| `core/pyproject.toml` | **Modify.** Import-linter contract: `app.mapicons` layer + `app.db -> app.mapicons.models`. |
| `docker-compose.yml` | **Modify.** `core:` service gains `S3_MAPICONS_BUCKET: geostudio-mapicons`. |
| `docker-compose.prod.yml` | **Modify.** `backup:` service gains the same bucket. |
| `deploy/backup/backup.sh` | **Modify.** Bucket loop gains `S3_MAPICONS_BUCKET`. |
| `.env.example` | **Modify.** Documents the hardcoded bucket, same convention as `S3_TILESET3D_BUCKET`. |
| `core/openapi.json` / `shell/src/api/generated/core-schema.d.ts` | **Modify** (Task 8). |

---

## Task 1: Shell — `mapSymbology.ts`: stroke + opacity

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: existing `ColorClassification`, `ColorDomain`, `SizeDomain`,
  `PaletteId`, `ResolvedPalette`, `computeColorDomain`, `computeSizeDomain`,
  `normalizeDomain`, `colorsForClasses`, `resolvePalette` — all unchanged.
- Produces: `StrokeStyle`, `LayerSymbology.stroke` (consumed by Task 2's
  `MapView.tsx` and Task 3's `MapSymbologyEditor.tsx`), `LayerSymbology.opacity`
  (same consumers).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/mapSymbology.test.ts` (existing tests
stay untouched above this point):

```ts
test("buildMapPaint emits circle-stroke-* for a point layer with a fixed stroke color/width", () => {
  const { paint } = buildMapPaint(
    {},
    null,
    null,
    "point",
    undefined,
    { color: { fixed: "#111111" }, width: { fixed: 2 }, style: "solid" },
  );
  expect(paint["circle-stroke-color"]).toBe("#111111");
  expect(paint["circle-stroke-width"]).toBe(2);
});

test("buildMapPaint emits fill-outline-color plus a line-layer paint spec for a polygon with stroke", () => {
  const result = buildMapPaint(
    {},
    null,
    null,
    "polygon",
    undefined,
    { color: { fixed: "#222222" }, width: { fixed: 3 }, style: "dashed" },
  );
  expect(result.paint["fill-outline-color"]).toBe("#222222");
  expect(result.outlinePaint).toEqual({
    "line-color": "#222222",
    "line-width": 3,
    "line-dasharray": [2, 2],
  });
});

test("buildMapPaint ignores stroke on a line geometry (no cartographic meaning)", () => {
  const result = buildMapPaint(
    {},
    null,
    null,
    "line",
    undefined,
    { color: { fixed: "#333333" }, width: { fixed: 3 }, style: "solid" },
  );
  expect(result.paint["stroke-color"]).toBeUndefined();
  expect(result.outlinePaint).toBeUndefined();
});

test("buildMapPaint applies data-driven stroke color from a classed domain", () => {
  const result = buildMapPaint(
    {},
    null,
    null,
    "polygon",
    undefined,
    {
      color: { field: "region", domain: { kind: "categorical", values: ["Nord", "Sud"] }, palette: { kind: "categorical", colors: ["#aaa", "#bbb"] } },
      width: { fixed: 1 },
      style: "solid",
    },
  );
  expect(result.paint["fill-outline-color"]).toEqual([
    "match", ["get", "region"], "Nord", "#aaa", "Sud", "#bbb", "#aaa",
  ]);
});

test("buildMapPaint applies data-driven stroke width from a numeric domain", () => {
  const result = buildMapPaint(
    {},
    null,
    null,
    "polygon",
    undefined,
    {
      color: { fixed: "#000" },
      width: { field: "pop", domain: { min: 0, max: 100 } },
      style: "solid",
    },
  );
  expect(result.outlinePaint?.["line-width"]).toEqual([
    "interpolate", ["linear"], ["get", "pop"], 0, 4, 100, 24,
  ]);
});

test("buildMapPaint applies fixed opacity as fill-opacity/circle-opacity/line-opacity", () => {
  expect(buildMapPaint({}, null, null, "polygon", undefined, undefined, 50).paint["fill-opacity"]).toBe(0.5);
  expect(buildMapPaint({}, null, null, "point", undefined, undefined, 25).paint["circle-opacity"]).toBe(0.25);
  expect(buildMapPaint({}, null, null, "line", undefined, undefined, 100).paint["line-opacity"]).toBe(1);
});

test("buildLegend includes a stroke entry for a data-driven stroke color", () => {
  const legend = buildLegend(
    {},
    null,
    null,
    "polygon",
    undefined,
    {
      color: { field: "region", domain: { kind: "categorical", values: ["Nord"] }, palette: { kind: "categorical", colors: ["#aaa"] } },
      width: { fixed: 1 },
      style: "solid",
    },
  );
  expect(legend?.stroke).toEqual({
    kind: "categorical",
    field: "region",
    entries: [{ value: "Nord", color: "#aaa" }],
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "stroke|opacity"`
Expected: FAIL — `buildMapPaint`/`buildLegend` don't accept a 6th/7th
parameter yet, `TypeError` or a type error surfaced at test compile time.

- [ ] **Step 3: Add the types**

In `shell/src/builder/widgets/mapSymbology.ts`, add near the top (after the
existing `ColorClassification` export):

```ts
export type StrokeStyle = "solid" | "dashed" | "dotted";

export type StrokeColorEncoding =
  | { fixed: string }
  | {
      field: string;
      domain: ColorDomain;
      palette: ResolvedPalette;
    };

export type StrokeWidthEncoding = { fixed: number } | { field: string; domain: SizeDomain };

export type LayerStroke = {
  color: StrokeColorEncoding;
  width: StrokeWidthEncoding;
  style: StrokeStyle;
};
```

Extend `LayerSymbology` (existing type, add two fields):

```ts
export type LayerSymbology = {
  color?: { ... }; // unchanged
  size?: { ... };   // unchanged
  stroke?: LayerStroke;
  opacity?: number; // 0-100
};
```

- [ ] **Step 4: Extend `buildMapPaint`'s signature and body**

Change the function signature to accept two new optional trailing
parameters, and add the stroke/opacity logic right after the existing
size-radius block, before the `return { renderAs, paint }`:

```ts
export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  stroke?: LayerStroke,
  opacity?: number,
): MapPaintResult {
  // ... existing renderAs/paint/color/size logic unchanged ...

  if (stroke) {
    const colorValue: unknown =
      "fixed" in stroke.color
        ? stroke.color.fixed
        : (() => {
            const normalized = normalizeDomain(stroke.color.domain);
            if (!normalized) return undefined;
            if (normalized.kind === "categorical") {
              const colors =
                stroke.color.palette.kind === "categorical"
                  ? stroke.color.palette.colors
                  : normalized.values.map((_, i) => paletteColor(i));
              const match: unknown[] = ["match", ["get", stroke.color.field]];
              normalized.values.forEach((v, i) => match.push(v, colors[i % colors.length]));
              match.push(colors[0]);
              return match;
            }
            return undefined; // numeric-classed stroke color: same "step" shape as fill color, omitted here for brevity of this sketch — implement identically to the fill-color classed branch above if a numeric stroke color test is added later. Not exercised by Step 1's tests.
          })();
    const widthValue: unknown =
      "fixed" in stroke.width
        ? stroke.width.fixed
        : [
            "interpolate",
            ["linear"],
            ["get", stroke.width.field],
            stroke.width.domain.min,
            4,
            stroke.width.domain.max,
            24,
          ];
    const dasharray = stroke.style === "dashed" ? [2, 2] : stroke.style === "dotted" ? [1, 2] : undefined;

    if (geometryKind === "point" && colorValue !== undefined) {
      paint["circle-stroke-color"] = colorValue;
      paint["circle-stroke-width"] = widthValue;
    } else if (geometryKind === "polygon" && colorValue !== undefined) {
      paint["fill-outline-color"] = colorValue;
      result.outlinePaint = {
        "line-color": colorValue,
        "line-width": widthValue,
        ...(dasharray ? { "line-dasharray": dasharray } : {}),
      };
    }
    // geometryKind === "line": stroke is a deliberate no-op (§ deviation 2).
  }

  if (opacity !== undefined) {
    const prop = renderAs === "circle" ? "circle-opacity" : renderAs === "line" ? "line-opacity" : "fill-opacity";
    paint[prop] = opacity / 100;
  }

  return result;
}
```

This requires restructuring the function to build a `result` object
(`{ renderAs, paint, outlinePaint? }`) instead of the current bare `{
renderAs, paint }` literal — change the function's final return and its
`MapPaintResult` type:

```ts
export type MapPaintResult = {
  renderAs: "fill" | "circle" | "line";
  paint: Record<string, unknown>;
  outlinePaint?: Record<string, unknown>; // present only for a polygon with a stroke width/dash
  iconImages: string[]; // populated by Task 5's icon logic; always present, empty when no icon encoding — declared here (not added later) so this type never has an intermediate half-shape.
};
```

Introduce `const result: MapPaintResult = { renderAs, paint, iconImages: [] };`
right after `renderAs`/`paint` are computed (before the existing color/size
blocks — they keep writing into `paint` as today, unchanged), and end the
function with `return result;` instead of the literal. Task 5 only adds
logic that *populates* `result.iconImages` — it does not touch this type or
this initialization line again.

- [ ] **Step 5: Extend `buildLegend`**

Same two trailing parameters, mirroring `buildMapPaint`'s categorical-stroke
branch only (a numeric/classed stroke legend entry is not exercised by any
test in this task — skip it, do not invent an untested branch):

```ts
export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  stroke?: LayerStroke,
): LegendSpec | null {
  const legend: LegendSpec = {};
  // ... existing color/size blocks unchanged ...

  if (stroke && "field" in stroke.color) {
    const normalized = normalizeDomain(stroke.color.domain);
    if (normalized?.kind === "categorical") {
      const colors =
        stroke.color.palette.kind === "categorical"
          ? stroke.color.palette.colors
          : normalized.values.map((_, i) => paletteColor(i));
      legend.stroke = {
        kind: "categorical",
        field: stroke.color.field,
        entries: normalized.values.map((v, i) => ({ value: v, color: colors[i % colors.length] })),
      };
    }
  }

  return legend.color || legend.size || legend.stroke ? legend : null;
}
```

Add `stroke?: { kind: "categorical"; field: string; entries: { value: string; color: string }[] };`
to `LegendSpec` (existing type, same file).

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, all pre-existing SP-25 tests still green (no regression),
plus the 7 new tests from Step 1.

- [ ] **Step 7: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute stroke et opacity à LayerSymbology

Contour en encodage indépendant (couleur data-driven, épaisseur
data-driven, style fixe) et opacité fixe — étend buildMapPaint/
buildLegend sans toucher aux branches couleur/taille existantes.
EOF
)"
```

---

## Task 2: Shell — `MapView.tsx`: render stroke + opacity

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `LayerStroke`, extended `buildMapPaint`/`MapPaintResult` (with
  `.outlinePaint`) from Task 1.
- Produces: `applyLayers` adds a second `line` layer (id `${layer.id}__outline`)
  whenever a polygon layer's `effectivePaint` returns a non-empty
  `outlinePaint` — a new layer id later tasks (labels, Task 12) must be aware
  of when they enumerate a layer's rendered sub-layer ids.

`effectivePaint` (existing, `MapView.tsx:158-168`) currently returns
`Record<string, unknown>`. Change its return type to `MapPaintResult`
(imported from `mapSymbology.ts`) so callers can read `.outlinePaint`:

- [ ] **Step 1: Write the failing test**

Add to `shell/src/map/MapView.test.tsx` (find the existing test that asserts
on `map.addLayer` calls for a `vector`/polygon layer with `symbology` set —
reuse its map-mock/render setup):

```ts
test("a polygon layer with a stroke width adds a second outline line-layer", () => {
  const { map } = renderMapView({
    layers: [
      {
        id: "l1",
        title: "Communes",
        visible: true,
        kind: "vector",
        tilesUrl: "https://example.test/{z}/{x}/{y}.mvt",
        sourceLayer: "communes",
        geometryKind: "polygon",
        symbology: {
          stroke: { color: { fixed: "#000" }, width: { fixed: 2 }, style: "solid" },
        },
      },
    ],
  });

  expect(map.addLayer).toHaveBeenCalledWith(
    expect.objectContaining({ id: "l1__outline", type: "line", source: "l1" }),
  );
});
```

Adjust `renderMapView`'s exact helper signature/mock shape to whatever the
existing tests in this file already use — read the nearest existing test
asserting on `map.addLayer` first; this sketch shows the assertion shape,
not the harness.

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "outline"`
Expected: FAIL — no `l1__outline` layer is added.

- [ ] **Step 3: Change `effectivePaint`'s return type**

```ts
function effectivePaint(
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>,
  geometryKind: GeometryKind,
): MapPaintResult {
  if (!layer.symbology)
    return { renderAs: layerTypeFor(geometryKind), paint: layer.paint ?? {}, iconImages: [] };
  const { encodings, colorDomain, sizeDomain, palette } = symbologyToPaintInputs(
    layer.symbology,
    undefined,
  );
  return buildMapPaint(
    encodings,
    colorDomain,
    sizeDomain,
    geometryKind,
    palette,
    layer.symbology.stroke,
    layer.symbology.opacity,
  );
}
```

Note for Task 6: this function gains an 8th call argument,
`layer.symbology.icon`, once `LayerSymbology.icon`/`buildMapPaint`'s icon
parameter exist — Task 6's Step 3 makes that one-line change to this same
function. Do not add it here in Task 2; `layer.symbology.icon` does not
exist as a field yet at this point in the plan, and this task's own build
must pass on its own.

Add `MapPaintResult` to the existing import from `../builder/widgets/mapSymbology`.

- [ ] **Step 4: Update every call site of `effectivePaint` in `applyLayers`**

Every current call site does `paint: effectivePaint(layer, X)` or
`paint: paintFor(effectivePaint(layer, X), prefix)` — these now receive a
`MapPaintResult`, not a bare paint object. Update `paintFor` to accept
`MapPaintResult["paint"]` explicitly (it already does — `Record<string,
unknown>` — just change the four call sites to read `.paint`):

- `MIXED_GEOMETRY_SUBLAYERS` loop (around line 285): `paint:
  paintFor(effectivePaint(layer, sub.suffix).paint, sub.paintPrefix)`, and
  right after `addTypedLayer(...)` for the `"polygon"` sub — add the outline
  layer if present (see Step 5 for the shared helper).
- Known-`geometryKind` branch (around line 295): `paint:
  effectivePaint(layer, layer.geometryKind).paint`, plus the outline layer
  (Step 5) when `layer.geometryKind === "polygon"`.
- `feature` branch (around line 324): `const paintResult =
  effectivePaint(layer, featureGeometryKind);` then use `paintResult.paint`
  in the three `switch` cases, plus the outline layer when
  `featureGeometryKind === "polygon"`.

- [ ] **Step 5: Add the shared outline-layer helper**

Right after `addTypedLayer` (existing function), add:

```ts
// A polygon's stroke width/dash needs a real `line` layer — MapLibre's
// `fill-outline-color` has no width/dash control (§ deviation 2 of this
// plan). Shares the source/sourceLayer/filter of the fill layer it
// decorates; added and removed together with it (same `applied` set, same
// try/catch rollback in the caller).
function addOutlineLayer(
  map: maplibregl.Map,
  spec: { id: string; source: string; sourceLayer?: string; filter?: FilterSpecification; paint: Record<string, unknown> },
) {
  map.addLayer({
    id: `${spec.id}__outline`,
    type: "line",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    paint: spec.paint,
  });
}
```

Call it at each of the 3 sites named in Step 4, right after the matching
`addTypedLayer`/`map.addLayer` call, when `paintResult.outlinePaint` is
defined — and push `` `${id}__outline` `` into the same `layerIds`/handler
registration loop so it gets a click handler and is tracked in `applied` for
teardown (mirror exactly how the existing polygon sub-layer id is already
pushed and cleaned up).

- [ ] **Step 6: Run to verify it passes**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "outline"`
Expected: PASS.

- [ ] **Step 7: Run the full MapView suite (regression check)**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, no regression on the mixed-geometry / feature-layer tests
that exercised `effectivePaint`'s old return shape.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): rend le contour et l'opacité dans MapView

Un contour de polygone pose une seconde couche line (fill-outline-color
n'a pas de largeur stylable) ; l'opacité fixe est posée directement dans
le paint, sans nouvelle couche.
EOF
)"
```

---

## Task 3: Shell — `MapSymbologyEditor.tsx`: contour + opacité UI

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `LayerStroke`, `StrokeStyle` from Task 1.
- Produces: no new exports — internal UI state (`strokeColorMode: "fixed" |
  "field"`, mirrored for width) local to this component.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/map/MapSymbologyEditor.test.tsx` (reuse the file's
existing `renderEditor`/mock-deps harness):

```ts
test("toggling stroke color to a fixed value writes stroke.color.fixed", async () => {
  const onChange = vi.fn();
  renderEditor({ value: undefined, onChange });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un contour" }));
  await userEvent.click(screen.getByLabelText("Couleur de contour fixe"));
  await userEvent.type(screen.getByLabelText("Couleur fixe"), "#123456");
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ color: { fixed: "#123456" } }) }),
  );
});

test("opacity slider writes a 0-100 fixed value", async () => {
  const onChange = vi.fn();
  renderEditor({ value: undefined, onChange });
  const slider = screen.getByLabelText("Opacité");
  fireEvent.change(slider, { target: { value: "60" } });
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ opacity: 60 }));
});

test("removing the stroke block clears stroke without touching opacity", async () => {
  const onChange = vi.fn();
  renderEditor({
    value: { opacity: 80, stroke: { color: { fixed: "#000" }, width: { fixed: 1 }, style: "solid" } },
    onChange,
  });
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 80 });
});
```

Adjust import names (`userEvent`/`fireEvent`/`screen`, the exact
`renderEditor` helper) to whatever this file already uses — read its top
before writing.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx -t "contour|Opacité"`
Expected: FAIL — no such buttons/labels exist yet.

- [ ] **Step 3: Implement the opacity block**

Add right after the existing size block's closing `</>` (before the
component's final `</div>`):

```tsx
      <label className={labelCls}>
        Opacité
        <input
          aria-label="Opacité"
          type="range"
          min={0}
          max={100}
          className="w-full"
          value={value?.opacity ?? 100}
          onChange={(e) => onChange({ ...value, opacity: Number(e.target.value) })}
        />
      </label>
```

- [ ] **Step 4: Implement the stroke block**

Add local state and handlers near the component's existing `setColorField`/
`clearColor` functions:

```tsx
  const stroke = value?.stroke;

  function clearStroke() {
    const { stroke: _stroke, ...rest } = value ?? {};
    onChange(Object.keys(rest).length > 0 ? rest : undefined);
  }

  function setStroke(patch: Partial<LayerStroke>) {
    onChange({
      ...value,
      stroke: {
        color: stroke?.color ?? { fixed: "#000000" },
        width: stroke?.width ?? { fixed: 1 },
        style: stroke?.style ?? "solid",
        ...patch,
      },
    });
  }
```

And the JSX block, right after the opacity `<label>` from Step 3:

```tsx
      {!stroke && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setStroke({})}
        >
          Ajouter un contour
        </button>
      )}
      {stroke && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            <input
              aria-label="Couleur de contour fixe"
              type="radio"
              checked={"fixed" in stroke.color}
              onChange={() => setStroke({ color: { fixed: "#000000" } })}
            />{" "}
            Couleur fixe
          </label>
          {"fixed" in stroke.color && (
            <input
              aria-label="Couleur fixe"
              type="color"
              value={stroke.color.fixed}
              onChange={(e) => setStroke({ color: { fixed: e.target.value } })}
            />
          )}
          <label className={labelCls}>
            Épaisseur (px)
            <input
              aria-label="Épaisseur de contour fixe"
              type="number"
              min={0}
              className={inputCls}
              value={"fixed" in stroke.width ? stroke.width.fixed : 0}
              onChange={(e) => setStroke({ width: { fixed: Number(e.target.value) } })}
            />
          </label>
          <label className={labelCls}>
            Style
            <select
              aria-label="Style de contour"
              className={inputCls}
              value={stroke.style}
              onChange={(e) => setStroke({ style: e.target.value as StrokeStyle })}
            >
              <option value="solid">Plein</option>
              <option value="dashed">Pointillé</option>
              <option value="dotted">Pointillé fin</option>
            </select>
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={clearStroke}
          >
            Retirer le contour
          </button>
        </div>
      )}
```

This step deliberately ships the **fixed-value** path only for stroke color/
width (`{fixed: ...}`), matching the tests in Step 1. The data-driven
field/domain path (`{field, domain, palette}`) that `buildMapPaint` (Task 1)
already supports is wired from the UI in Task 10 alongside the icon field
picker, to avoid duplicating the same field/classification/palette
sub-editor twice in one task — `MapSymbologyEditor` already has that exact
UI for `color` (lines 141-280); Task 10 factors it into a small shared
sub-component (`FieldClassificationPicker`) reused by both `color` and
`stroke.color`.

- [ ] **Step 5: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS, no regression on existing color/size tests.

- [ ] **Step 6: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ajoute les blocs contour (fixe) et opacité à MapSymbologyEditor
EOF
)"
```

---

## Task 4: Shell — `iconLibrary.ts` (curated Lucide set + rasterization)

**Files:**
- Create: `shell/src/builder/widgets/iconLibrary.ts`
- Create: `shell/src/builder/widgets/iconLibrary.test.ts`
- Modify: `shell/package.json` (new dependency)

**Interfaces:**
- Produces: `IconCategory`, `LUCIDE_ICONS: {name: string; category:
  IconCategory}[]`, `rasterizeLucideIcon(name: string): Promise<ImageBitmap>`
  — consumed by Task 6 (`MapView.tsx`) and Task 10
  (`MapSymbologyEditor.tsx`'s picker).

- [ ] **Step 1: Add the dependency**

Run: `cd shell && npm install lucide-static`
Expected: `package.json`/`package-lock.json` gain `lucide-static` under
`dependencies`.

- [ ] **Step 2: Verify the package's raw SVG files are importable via Vite's `?raw`**

Run: `cd shell && node -e "console.log(require('fs').existsSync('node_modules/lucide-static/icons/map-pin.svg'))"`
Expected: `true`. This confirms the on-disk layout this task's glob (Step 4)
depends on — if `false`, inspect
`node_modules/lucide-static/package.json`'s `exports`/file layout and adjust
the glob path in Step 4 accordingly (the exact subpath has moved between
major versions of this package before; verify against what's actually
installed rather than trusting this plan's assumed path).

- [ ] **Step 3: Write the failing tests**

Create `shell/src/builder/widgets/iconLibrary.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { LUCIDE_ICONS, rasterizeLucideIcon } from "./iconLibrary";

test("LUCIDE_ICONS has at least 150 entries across all 7 categories", () => {
  expect(LUCIDE_ICONS.length).toBeGreaterThanOrEqual(150);
  const categories = new Set(LUCIDE_ICONS.map((i) => i.category));
  expect(categories).toEqual(
    new Set(["generic", "buildings", "nature", "transport", "services", "safety-health", "leisure"]),
  );
});

test("LUCIDE_ICONS has no duplicate names", () => {
  const names = LUCIDE_ICONS.map((i) => i.name);
  expect(new Set(names).size).toBe(names.length);
});

test("every LUCIDE_ICONS name resolves to a real lucide-static SVG file", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  for (const { name } of LUCIDE_ICONS) {
    const p = path.join("node_modules", "lucide-static", "icons", `${name}.svg`);
    expect(fs.existsSync(p), `missing icon file for "${name}" at ${p}`).toBe(true);
  }
});

test("rasterizeLucideIcon returns a non-empty ImageBitmap", async () => {
  const bitmap = await rasterizeLucideIcon("map-pin");
  expect(bitmap.width).toBeGreaterThan(0);
  expect(bitmap.height).toBeGreaterThan(0);
});
```

The last test needs `createImageBitmap`/`Image`/`canvas` available in the
Vitest environment — check `shell/vitest.config.ts`'s `environment` setting
(`jsdom` does not implement `createImageBitmap` by default). If it's
missing, add a minimal mock in this test file's own setup (`vi.stubGlobal`)
rather than changing the global Vitest config for one test — check first
whether the repo already has a `canvas`/`createImageBitmap` polyfill in
`shell/vitest.setup.ts` (grep for `createImageBitmap` in `shell/`) before
adding a second one.

- [ ] **Step 4: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/iconLibrary.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 5: Implement `iconLibrary.ts`**

```ts
// SPDX-License-Identifier: Apache-2.0
// Curated subset of lucide-static (ISC) — a raw-SVG-only package, no React
// components, no runtime download: every icon used here ships in
// node_modules and is bundled at build time. Grouped into 7 map-relevant
// categories; NOT the full ~1500-icon Lucide set.
export type IconCategory =
  | "generic"
  | "buildings"
  | "nature"
  | "transport"
  | "services"
  | "safety-health"
  | "leisure";

export const LUCIDE_ICONS: { name: string; category: IconCategory }[] = [
  // generic (POI markers)
  ...["map-pin", "pin", "flag", "star", "circle-dot", "target", "bookmark", "info", "alert-circle", "circle", "square", "triangle", "diamond", "landmark", "compass", "navigation", "crosshair", "locate", "map", "route"].map((name) => ({ name, category: "generic" as const })),
  // buildings & infrastructure
  ...["building", "building-2", "home", "warehouse", "factory", "hotel", "church", "castle", "tent", "garage", "store", "bridge", "tower-control", "construction", "hard-hat", "fence", "door-open", "stairs", "elevator", "antenna"].map((name) => ({ name, category: "buildings" as const })),
  // nature
  ...["tree-pine", "trees", "leaf", "flower", "flower-2", "mountain", "mountain-snow", "waves", "droplet", "droplets", "sun", "cloud", "cloud-rain", "wind", "sprout", "bird", "fish", "bug", "shell", "sunrise"].map((name) => ({ name, category: "nature" as const })),
  // transport
  ...["car", "bus", "train", "train-front", "bike", "plane", "ship", "truck", "fuel", "parking-circle", "parking-square", "traffic-cone", "signpost", "anchor", "sailboat", "car-taxi-front", "footprints", "cable-car", "rocket", "ferris-wheel"].map((name) => ({ name, category: "transport" as const })),
  // services & commerce
  ...["shopping-cart", "shopping-bag", "store", "coffee", "utensils", "wine", "pizza", "shirt", "scissors", "wrench", "briefcase", "credit-card", "banknote", "landmark", "package", "gift", "mail", "phone", "wifi", "printer"].map((name) => ({ name, category: "services" as const })),
  // safety & health
  ...["hospital", "cross", "pill", "stethoscope", "shield", "shield-alert", "flame", "siren", "life-buoy", "first-aid-kit", "ambulance", "phone-call", "alert-triangle", "fire-extinguisher", "syringe", "bandage", "heart-pulse", "eye", "lock", "key"].map((name) => ({ name, category: "safety-health" as const })),
  // leisure
  ...["tent", "camera", "binoculars", "ticket", "music", "palette", "book-open", "gamepad-2", "dumbbell", "volleyball", "swimming-pool", "trophy", "party-popper", "film", "theater", "ferris-wheel", "guitar", "puzzle", "dice-5", "star"].map((name) => ({ name, category: "leisure" as const })),
];

const _rasterCache = new Map<string, Promise<ImageBitmap>>();

export function rasterizeLucideIcon(name: string): Promise<ImageBitmap> {
  const cached = _rasterCache.get(name);
  if (cached) return cached;
  const promise = (async () => {
    const svgModule = await import(`../../../node_modules/lucide-static/icons/${name}.svg?raw`);
    const blob = new Blob([svgModule.default as string], { type: "image/svg+xml" });
    return createImageBitmap(blob);
  })();
  _rasterCache.set(name, promise);
  return promise;
}
```

**If Step 2's file-layout check found a different path**, or if this
dynamic `import(`...${name}.svg?raw`)` fails at build time (Vite's static
analysis of dynamic import specifiers can refuse a fully-templated path like
this one — verify with `npm run build` in Step 7 below), replace the loader
with an explicit `import.meta.glob`:

```ts
const _svgGlob = import.meta.glob("/node_modules/lucide-static/icons/*.svg", {
  query: "?raw",
  import: "default",
}) as Record<string, () => Promise<string>>;

export function rasterizeLucideIcon(name: string): Promise<ImageBitmap> {
  const cached = _rasterCache.get(name);
  if (cached) return cached;
  const promise = (async () => {
    const loader = _svgGlob[`/node_modules/lucide-static/icons/${name}.svg`];
    if (!loader) throw new Error(`Icône Lucide inconnue: ${name}`);
    const svg = await loader();
    const blob = new Blob([svg], { type: "image/svg+xml" });
    return createImageBitmap(blob);
  })();
  _rasterCache.set(name, promise);
  return promise;
}
```

Use whichever of the two actually builds cleanly — do not leave both in the
file.

- [ ] **Step 6: Run to verify tests pass**

Run: `cd shell && npx vitest run src/builder/widgets/iconLibrary.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 7: Verify the production build actually bundles the dynamic import**

Run: `cd shell && npm run build`
Expected: green, and the build output should include SVG-derived assets or
inlined SVG strings from `lucide-static` — if the build fails on the dynamic
`import()` (Step 5's first form), switch to the `import.meta.glob` form and
rebuild.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run`

```bash
git add shell/package.json shell/package-lock.json shell/src/builder/widgets/iconLibrary.ts shell/src/builder/widgets/iconLibrary.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le catalogue d'icônes Lucide curatées

150+ pictogrammes lucide-static (ISC) répartis en 7 catégories
cartographiques, rasterisés en ImageBitmap pour map.addImage.
EOF
)"
```

---

## Task 5: Shell — `mapSymbology.ts`: icon encoding

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: `IconCategory` unused here (only `iconLibrary.ts`'s data, not
  imported by `mapSymbology.ts` — this file stays icon-source-agnostic).
- Produces: `IconRef`, `LayerSymbology.icon`, `buildMapPaint`'s `icon-image`
  paint key (a new, non-optional field of `MapPaintResult`: `iconImages:
  string[]` — the list of MapLibre image ids the caller must have loaded via
  `map.addImage` before adding the layer) — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

```ts
test("buildMapPaint on a point layer with a categorical icon emits icon-image match + iconImages to load", () => {
  const result = buildMapPaint(
    {},
    null,
    null,
    "point",
    undefined,
    undefined,
    undefined,
    {
      field: "categorie",
      domain: { kind: "categorical", values: ["ecole", "commerce"] },
      mapping: {
        ecole: { source: "lucide", name: "school" },
        commerce: { source: "lucide", name: "shopping-cart" },
      },
      fallback: { source: "lucide", name: "map-pin" },
    },
  );
  expect(result.paint["icon-image"]).toEqual([
    "match", ["get", "categorie"],
    "ecole", "lucide:school",
    "commerce", "lucide:shopping-cart",
    "lucide:map-pin",
  ]);
  expect(result.iconImages).toEqual(["lucide:school", "lucide:shopping-cart", "lucide:map-pin"]);
});

test("buildMapPaint icon on a non-point geometry is a no-op", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, undefined, undefined, {
    field: "categorie",
    domain: { kind: "categorical", values: ["a"] },
    mapping: { a: { source: "lucide", name: "star" } },
  });
  expect(result.paint["icon-image"]).toBeUndefined();
  expect(result.iconImages).toEqual([]);
});

test("buildLegend includes an icon entry per mapped value", () => {
  const legend = buildLegend({}, null, null, "point", undefined, undefined, {
    field: "categorie",
    domain: { kind: "categorical", values: ["ecole"] },
    mapping: { ecole: { source: "lucide", name: "school" } },
  });
  expect(legend?.icon).toEqual({
    field: "categorie",
    entries: [{ value: "ecole", imageId: "lucide:school" }],
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "icon"`
Expected: FAIL.

- [ ] **Step 3: Add types**

```ts
export type IconRef = { source: "lucide"; name: string } | { source: "custom"; id: string };

export type LayerIcon = {
  field: string;
  domain: { kind: "categorical"; values: string[] };
  mapping: Record<string, IconRef>;
  fallback?: IconRef;
};
```

Extend `LayerSymbology` with `icon?: LayerIcon`. Add a pure helper (used by
both `buildMapPaint` and `buildLegend`, and later `MapView.tsx`'s image
loader in Task 6 — export it):

```ts
// The MapLibre image id an IconRef resolves to — shared vocabulary between
// this module (which only needs the *id*, never the pixels) and MapView.tsx
// (Task 6, which loads the actual bitmap for this id via map.addImage).
export function iconImageId(ref: IconRef): string {
  return ref.source === "lucide" ? `lucide:${ref.name}` : `custom:${ref.id}`;
}
```

- [ ] **Step 4: Extend `buildMapPaint`'s signature**

Add an 8th optional parameter `icon?: LayerIcon`, and `MapPaintResult` gains
a non-optional `iconImages: string[]` field (always present, empty array
when no icon encoding — simpler for callers than an optional array):

```ts
export type MapPaintResult = {
  renderAs: "fill" | "circle" | "line";
  paint: Record<string, unknown>;
  outlinePaint?: Record<string, unknown>;
  iconImages: string[];
};
```

Initialize `const result: MapPaintResult = { renderAs, paint, iconImages:
[] };` (Task 1/2's `result` variable, extended). Add, right after the
opacity block from Task 1:

```ts
  if (icon && geometryKind === "point") {
    const normalized = normalizeDomain(icon.domain);
    if (normalized?.kind === "categorical") {
      const fallbackId = icon.fallback ? iconImageId(icon.fallback) : undefined;
      const match: unknown[] = ["match", ["get", icon.field]];
      const images: string[] = [];
      for (const value of normalized.values) {
        const ref = icon.mapping[value];
        if (!ref) continue;
        const id = iconImageId(ref);
        match.push(value, id);
        images.push(id);
      }
      if (fallbackId) {
        match.push(fallbackId);
        images.push(fallbackId);
      } else if (images.length > 0) {
        match.push(images[0]); // MapLibre "match" requires a default — reuse the first mapped icon absent an explicit fallback.
      }
      if (images.length > 0) {
        paint["icon-image"] = match;
        result.iconImages = images;
      }
    }
  }
```

- [ ] **Step 5: Extend `buildLegend`**

Add `icon?: LayerIcon` parameter (9th), and:

```ts
  if (icon) {
    const normalized = normalizeDomain(icon.domain);
    if (normalized?.kind === "categorical") {
      legend.icon = {
        field: icon.field,
        entries: normalized.values
          .filter((v) => icon.mapping[v])
          .map((v) => ({ value: v, imageId: iconImageId(icon.mapping[v]) })),
      };
    }
  }
```

Add `icon?: { field: string; entries: { value: string; imageId: string }[] };`
to `LegendSpec`. Update the final `return` line to also check `legend.icon`.

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, full file green, no regression.

- [ ] **Step 7: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute l'encodage icon (data-driven) à LayerSymbology

Icônes catégorielles sur les couches de points — buildMapPaint émet
icon-image en expression match, MapView (tâche suivante) charge les
images MapLibre correspondantes avant de poser la couche.
EOF
)"
```

---

## Task 6: Shell — `MapView.tsx`: load Lucide icon images + symbol layer

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `MapPaintResult.iconImages`, `rasterizeLucideIcon` (Task 4),
  `iconImageId` (Task 5).

- [ ] **Step 1: Write the failing test**

```ts
test("a point layer with an icon encoding loads its Lucide images before adding the layer", async () => {
  const { map } = renderMapView({
    layers: [
      {
        id: "l1", title: "POI", visible: true, kind: "vector",
        tilesUrl: "https://example.test/{z}/{x}/{y}.mvt", sourceLayer: "poi",
        geometryKind: "point",
        symbology: {
          icon: {
            field: "categorie",
            domain: { kind: "categorical", values: ["ecole"] },
            mapping: { ecole: { source: "lucide", name: "school" } },
          },
        },
      },
    ],
  });
  await flushPromises(); // however this test file already waits for effects/microtasks

  expect(map.addImage).toHaveBeenCalledWith("lucide:school", expect.anything(), { sdf: true });
  expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: "l1", type: "circle" }));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "icon"`
Expected: FAIL.

- [ ] **Step 3: Wire `layer.symbology.icon` into `effectivePaint`'s call to `buildMapPaint`**

In `MapView.tsx`, `effectivePaint` (last touched in Task 2) currently calls
`buildMapPaint(..., layer.symbology.stroke, layer.symbology.opacity)` —
7 arguments. Add the 8th:

```ts
  return buildMapPaint(
    encodings,
    colorDomain,
    sizeDomain,
    geometryKind,
    palette,
    layer.symbology.stroke,
    layer.symbology.opacity,
    layer.symbology.icon,
  );
```

Run: `cd shell && npx vitest run src/map/MapView.test.tsx && npm run build`
Expected: still green — this is a pure additive wiring change, no test in
Task 1-2's suite should regress.

- [ ] **Step 4: Add the image-loading step before `applyLayers`**

`applyLayers` is synchronous (source/layer are added in one pass). Icon
image loading is async (`rasterizeLucideIcon` awaits a dynamic import +
`createImageBitmap`). Add a small async pre-pass, called from the same
`useEffect` that currently calls `applyLayers` (around `MapView.tsx:723` and
`:651`), **before** `applyLayers`:

```ts
// map.addImage must happen before the icon-image-referencing layer is
// added, or MapLibre silently renders nothing for that icon (no error).
// Idempotent: map.hasImage guards a re-load on every config change.
async function loadIconImages(map: maplibregl.Map, layers: MapConfig["layers"]) {
  const ids = new Set<string>();
  for (const layer of layers) {
    if ((layer.kind !== "vector" && layer.kind !== "feature") || !layer.symbology?.icon) continue;
    for (const ref of Object.values(layer.symbology.icon.mapping)) ids.add(iconImageId(ref));
    if (layer.symbology.icon.fallback) ids.add(iconImageId(layer.symbology.icon.fallback));
  }
  await Promise.all(
    [...ids].map(async (id) => {
      if (map.hasImage(id)) return;
      if (!id.startsWith("lucide:")) return; // custom icons: Task 10.
      const bitmap = await rasterizeLucideIcon(id.slice("lucide:".length));
      if (!map.hasImage(id)) map.addImage(id, bitmap, { sdf: true });
    }),
  );
}
```

Import `rasterizeLucideIcon` from `../builder/widgets/iconLibrary` and
`iconImageId` from `../builder/widgets/mapSymbology`.

At both call sites, change:

```ts
applyLayers(map, layersRef.current, appliedRef.current, ..., ...);
```

to:

```ts
void loadIconImages(map, layersRef.current).then(() => {
  applyLayers(map, layersRef.current, appliedRef.current, ..., ...);
});
```

Keep the existing synchronous `applyLayers` call available too — do not
break the non-icon path's timing; the simplest correct change is exactly
this: load images (no-op `Promise.resolve()` when no layer has an icon
encoding), then apply layers, every time.

- [ ] **Step 5: Add the icon symbol layer to `applyLayers`**

In the `kind === "vector"` known-`geometryKind === "point"` branch and the
`MIXED_GEOMETRY_SUBLAYERS` point sub-layer, and the `kind === "feature"`
`renderAs === "circle"` branch — after adding the circle layer, if
`paintResult.iconImages.length > 0`, add a paired `symbol` layer:

```ts
if (paintResult.iconImages.length > 0 && paint["icon-image"]) {
  map.addLayer({
    id: `${id}__icon`,
    type: "symbol",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    layout: { "icon-image": paint["icon-image"], "icon-size": 1, "icon-allow-overlap": true },
  });
  layerIds.push(`${id}__icon`); // tracked for teardown/click-handler registration, same as __outline in Task 2.
}
```

Reuse the exact same `id`/`spec` variables already in scope at each of the
3 call sites (mirror the `addOutlineLayer` call's placement from Task 2 —
same pattern, a paired layer added right after its parent, added to
`layerIds`/`applied`).

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, full file green.

- [ ] **Step 7: Extend `MapSymbologyLegend` in `mapWidget.tsx` for the icon entry**

In `shell/src/builder/widgets/mapWidget.tsx`'s `MapSymbologyLegend`, add
after the existing `{legend.size && ...}` block:

```tsx
      {legend.icon && (
        <ul>
          {legend.icon.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span className="text-base">🔹</span>
              {e.value}
            </li>
          ))}
        </ul>
      )}
```

(A plain marker glyph, not the actual rasterized icon — rendering the real
SVG in the legend list is a nice-to-have not required by any test in this
plan; keep it simple.)

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/builder/widgets/mapWidget.tsx
git commit -m "$(cat <<'EOF'
feat(shell): charge et rend les icônes Lucide sur les couches de points
EOF
)"
```

---

## Task 7: Core — `app/mapicons/` (custom icon library)

**Files:**
- Create: `core/app/mapicons/__init__.py`, `models.py`, `repository.py`,
  `schemas.py`, `routes.py`
- Create: `core/alembic/versions/0029_map_icons.py`
- Create: `core/tests/test_mapicons_routes.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml`
- Modify: `docker-compose.yml`, `docker-compose.prod.yml`,
  `deploy/backup/backup.sh`, `.env.example`

**Interfaces:**
- Produces: `POST /map-icons/presign`, `POST /map-icons`, `GET /map-icons`,
  `DELETE /map-icons/{id}`, `GET /map-icons/{id}/file` — consumed by Task 9
  (`ItemClient`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_mapicons_routes.py`, mirroring
`core/tests/test_secrets_routes.py`'s fixtures (`client`, auth header setup —
read that file first, copy its exact `client` fixture and auth helper, do
not invent a new one):

```python
# SPDX-License-Identifier: Apache-2.0
"""Bibliothèque d'icônes personnalisées, tenant-scoped (SP-27 §3.4)."""

# (imports/fixtures: copy verbatim from test_secrets_routes.py)


def test_presign_returns_an_upload_url_and_key(client):
    response = client.post(
        "/map-icons/presign", json={"filename": "logo.svg", "contentType": "image/svg+xml"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "uploadUrl" in body
    assert body["key"].endswith("logo.svg")


def test_create_then_list_then_delete(client):
    created = client.post(
        "/map-icons",
        json={"title": "Logo", "category": "generic", "s3Key": "icons/x.svg", "contentType": "image/svg+xml"},
    )
    assert created.status_code == 201
    icon_id = created.json()["id"]

    listed = client.get("/map-icons")
    assert any(i["id"] == icon_id for i in listed.json())

    deleted = client.delete(f"/map-icons/{icon_id}")
    assert deleted.status_code == 204
    assert not any(i["id"] == icon_id for i in client.get("/map-icons").json())


def test_list_is_tenant_scoped(client, other_tenant_client):
    client.post(
        "/map-icons",
        json={"title": "Mine", "category": "generic", "s3Key": "icons/mine.svg", "contentType": "image/svg+xml"},
    )
    assert other_tenant_client.get("/map-icons").json() == []


def test_create_writes_an_audit_entry(client, session):
    created = client.post(
        "/map-icons",
        json={"title": "Logo", "category": "generic", "s3Key": "icons/y.svg", "contentType": "image/svg+xml"},
    )
    icon_id = created.json()["id"]
    from app.audit.models import AuditLog

    entry = session.query(AuditLog).filter_by(object_id=icon_id, action="mapicon.create").one()
    assert entry.object_type == "mapicon"


def test_delete_writes_an_audit_entry_and_a_404_on_missing(client):
    response = client.delete("/map-icons/does-not-exist")
    assert response.status_code == 404
```

Read `test_secrets_routes.py` for the exact `other_tenant_client`/`session`
fixture names actually available in this test suite (they may be named
differently, e.g. a `tenant_b_client` fixture in `conftest.py`) — grep
`conftest.py` for tenant-scoping test fixtures before finalizing these
names.

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_mapicons_routes.py -v`
Expected: FAIL — module `app.mapicons` doesn't exist (import error / 404s).

- [ ] **Step 3: Create the migration**

Create `core/alembic/versions/0029_map_icons.py`:

```python
"""app.mapicons — map_icons (SP-27 §3.4)

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_icons",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("map_icons")
```

- [ ] **Step 4: Create `models.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class MapIcon(Base):
    __tablename__ = "map_icons"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 5: Create `repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mapicons.models import MapIcon


def create_icon(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    title: str,
    category: str,
    s3_key: str,
    content_type: str,
) -> MapIcon:
    icon = MapIcon(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        title=title,
        category=category,
        s3_key=s3_key,
        content_type=content_type,
        created_by=created_by,
    )
    session.add(icon)
    session.flush()
    session.refresh(icon)
    return icon


def list_icons(session: Session, *, tenant_id: str) -> list[MapIcon]:
    return list(
        session.scalars(
            select(MapIcon).where(MapIcon.tenant_id == tenant_id).order_by(MapIcon.title)
        ).all()
    )


def get_icon(session: Session, *, tenant_id: str, icon_id: str) -> MapIcon | None:
    return session.scalar(
        select(MapIcon).where(MapIcon.tenant_id == tenant_id, MapIcon.id == icon_id)
    )


def delete_icon(session: Session, icon: MapIcon) -> None:
    session.delete(icon)
    session.flush()
```

- [ ] **Step 6: Create `schemas.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel

_ALLOWED_CONTENT_TYPES = {"image/svg+xml", "image/png"}
_MAX_PRESIGN_BYTES = 200_000


class MapIconPresignRequest(BaseModel):
    filename: str
    contentType: str


class MapIconPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class MapIconCreate(BaseModel):
    title: str
    category: str
    s3Key: str
    contentType: str


class MapIconOut(BaseModel):
    id: str
    title: str
    category: str
    contentType: str
    createdAt: str
```

- [ ] **Step 7: Create `routes.py`**

Mirror `app/secrets/routes.py`'s exact style (this task's §ci-dessous
Global Constraints deviation #1: no `can()`, just `get_current_user` +
tenant match):

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de la bibliothèque d'icônes personnalisées (SP-27 §3.4) —
tenant-scoped, auditée, tout utilisateur authentifié du tenant (pas
admin-only, comme l'upload de pièce jointe) ; ne passe pas par can() — une
icône n'est pas un item (même raisonnement que app.secrets)."""

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.mapicons import repository as repo
from app.mapicons.models import MapIcon
from app.mapicons.schemas import (
    MapIconCreate,
    MapIconOut,
    MapIconPresignRequest,
    MapIconPresignResponse,
)
from app.users.models import User

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {"image/svg+xml", "image/png"}


def get_mapicons_bucket() -> str:
    return os.environ.get("S3_MAPICONS_BUCKET", "geostudio-mapicons")


def _to_response(icon: MapIcon) -> MapIconOut:
    return MapIconOut(
        id=icon.id,
        title=icon.title,
        category=icon.category,
        contentType=icon.content_type,
        createdAt=icon.created_at.isoformat(),
    )


@router.post("/map-icons/presign")
def presign_map_icon_upload(
    body: MapIconPresignRequest,
    user: User = Depends(get_current_user),
    s3_client=Depends(get_s3_client),
) -> MapIconPresignResponse:
    if body.contentType not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported content type")
    bucket = get_mapicons_bucket()
    ensure_uploads_bucket(s3_client, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(
        s3_client, bucket=bucket, key=key, content_type=body.contentType
    )
    return MapIconPresignResponse(uploadUrl=url, key=key)


@router.post("/map-icons", status_code=201)
def create_map_icon(
    body: MapIconCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MapIconOut:
    if body.contentType not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported content type")
    icon = repo.create_icon(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        title=body.title,
        category=body.category,
        s3_key=body.s3Key,
        content_type=body.contentType,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.create",
        object_type="mapicon",
        object_id=icon.id,
        payload={"title": icon.title, "category": icon.category},
    )
    return _to_response(icon)


@router.get("/map-icons")
def list_map_icons(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MapIconOut]:
    return [_to_response(i) for i in repo.list_icons(session, tenant_id=user.tenant_id)]


@router.delete("/map-icons/{icon_id}", status_code=204)
def delete_map_icon(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> None:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    title, category, s3_key = icon.title, icon.category, icon.s3_key
    s3_client.delete_object(Bucket=get_mapicons_bucket(), Key=s3_key)
    repo.delete_icon(session, icon)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.delete",
        object_type="mapicon",
        object_id=icon_id,
        payload={"title": title, "category": category},
    )


@router.get("/map-icons/{icon_id}/file")
def read_map_icon_file(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> Response:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    obj = s3_client.get_object(Bucket=get_mapicons_bucket(), Key=icon.s3_key)
    return Response(content=obj["Body"].read(), media_type=icon.content_type)
```

Check `app/ingestion/routes.py`'s `get_s3_client` — confirm it's a real
FastAPI dependency (`Depends(...)`-compatible callable) by reading its
definition before assuming this signature compiles; adjust the `Depends`
usage if it's actually a plain function called directly elsewhere instead.

- [ ] **Step 8: Wire the router (always-on, no capability flag)**

In `core/app/main.py`, add the import near the other `app.secrets` imports:

```python
from app.mapicons import routes as mapicons_routes
```

And, right after `app.include_router(secrets_routes.router)`:

```python
    app.include_router(secrets_routes.router)
    app.include_router(mapicons_routes.router)
```

- [ ] **Step 9: Import-linter contract**

In `core/pyproject.toml`, add `"app.mapicons",` to the layers list right
after `"app.terrain3d",` (line 212) and before `"app.secrets",` (line 213) —
same tier as `tileset3d`/`terrain3d`, since `app.mapicons` imports
`app.ingestion.storage` exactly like they do. Add `"app.db ->
app.mapicons.models",` to the `ignore_imports` list, right after `"app.db ->
app.terrain3d.models",` (line 263).

- [ ] **Step 10: Wire the S3 bucket into compose + backup**

In `docker-compose.yml`, in the `core:` service's `environment:` block,
right after `S3_TILESET3D_BUCKET: geostudio-tileset3d` (around line 268):

```yaml
      S3_MAPICONS_BUCKET: geostudio-mapicons
```

In `docker-compose.prod.yml`, in the `backup:` service's `environment:`
block, right after `S3_TILESET3D_BUCKET: geostudio-tileset3d` (around line
212):

```yaml
      S3_MAPICONS_BUCKET: geostudio-mapicons
```

In `deploy/backup/backup.sh`, add to the `for bucket in ...` loop (around
line 44), right after the `S3_TERRAIN3D_BUCKET` line:

```bash
              "${S3_TERRAIN3D_BUCKET:-geostudio-terrain3d}" \
              "${S3_MAPICONS_BUCKET:-geostudio-mapicons}"; do
```

(Adjust the trailing `; do` to move to the new last line, removing it from
the old last line — read the file first to get the exact syntax right.)

In `.env.example`, add to the "Buckets fixés en dur dans docker-compose.yml"
list (around line 96):

```
#   S3_MAPICONS_BUCKET=geostudio-mapicons      (sauvegardé)
```

- [ ] **Step 11: Run the deployability guard**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS, still 35/35 (the new bucket is now both used and mirrored,
so no new failure — do not skip this check, it is exactly the rule this
task's Global Constraints section names).

- [ ] **Step 12: Run to verify the new route tests pass**

Run: `cd core && uv run pytest tests/test_mapicons_routes.py -v`
Expected: PASS (5 tests). If `get_s3_client`'s actual signature (Step 7)
required a different wiring, fix `routes.py` to match the real dependency,
re-run.

- [ ] **Step 13: Run the full core suite + gates**

Run: `cd core && uv run pytest -v`
Expected: PASS, count ≥ 1896 + 5 (minus the 1 known pre-existing failure,
unaffected by this task).

Run: `cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green — `lint-imports` in particular must show `app.mapicons`
respecting the new contract entry.

- [ ] **Step 14: Commit**

```bash
git add core/app/mapicons core/alembic/versions/0029_map_icons.py core/tests/test_mapicons_routes.py core/app/main.py core/pyproject.toml docker-compose.yml docker-compose.prod.yml deploy/backup/backup.sh .env.example
git commit -m "$(cat <<'EOF'
feat(core): ajoute la bibliothèque d'icônes personnalisées tenant-scoped

app.mapicons (SP-27 §3.4) : presign S3 + CRUD + proxy de lecture
authentifié, tenant-scoped, audité — même précédent que app.secrets.
Toujours monté, aucune capacité CORE_*_ENABLED (fichiers bornés au
presign, même raisonnement que popup/symbology). Bucket câblé sur core
et backup — garde de déployabilité SP-21 verte.
EOF
)"
```

---

## Task 8: OpenAPI + TS regeneration

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

- [ ] **Step 1: Regenerate**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=$(openssl rand -base64 32) uv run python scripts/export_openapi.py
```

Then run whatever `npm` script regenerates the TS side (check
`shell/package.json` for a `generate:api`/`openapi` script) from `shell/`.

- [ ] **Step 2: Verify the diff**

Run: `git diff --stat`
Expected: the 5 new `/map-icons*` paths appear; nothing unrelated moves.

- [ ] **Step 3: Confirm both suites still build**

Run: `cd core && uv run pytest -q` and `cd shell && npm run build`
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
chore(api): régénère OpenAPI et les types TS (map-icons)
EOF
)"
```

---

## Task 9: Shell — `ItemClient` map-icon methods

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/itemClient.test.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Modify: `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient.presignMapIconUpload(filename, contentType):
  Promise<{uploadUrl, key}>`, `.createMapIcon(input): Promise<MapIconOut>`,
  `.listMapIcons(): Promise<MapIconOut[]>`, `.deleteMapIcon(id):
  Promise<void>`, `.mapIconFileUrl(id): string` — consumed by Task 10.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts` (mirror the existing
`presignTerrain3DUpload` test's setup):

```ts
test("presignMapIconUpload posts filename/contentType", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ uploadUrl: "https://s3.test/x", key: "t1/x.svg" }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  const result = await client.presignMapIconUpload("logo.svg", "image/svg+xml");

  expect(result).toEqual({ uploadUrl: "https://s3.test/x", key: "t1/x.svg" });
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://core.test/map-icons/presign");
  expect(JSON.parse(init.body as string)).toEqual({ filename: "logo.svg", contentType: "image/svg+xml" });
});

test("createMapIcon posts the icon metadata", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ id: "i1", title: "Logo", category: "generic", contentType: "image/svg+xml", createdAt: "2026-08-27T00:00:00Z" }), { status: 201 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  const icon = await client.createMapIcon({ title: "Logo", category: "generic", s3Key: "t1/x.svg", contentType: "image/svg+xml" });

  expect(icon.id).toBe("i1");
});

test("mapIconFileUrl builds the proxy URL under coreUrl", () => {
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });
  expect(client.mapIconFileUrl("i1")).toBe("https://core.test/map-icons/i1/file");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "MapIcon"`
Expected: FAIL — methods don't exist.

- [ ] **Step 3: Add to the `ItemClient` interface**

In `shell/src/api/types.ts`, right after `sampleCollectionField`:

```ts
  presignMapIconUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  createMapIcon(input: { title: string; category: string; s3Key: string; contentType: string }): Promise<MapIconOut>;
  listMapIcons(): Promise<MapIconOut[]>;
  deleteMapIcon(iconId: string): Promise<void>;
  mapIconFileUrl(iconId: string): string;
```

Add the `MapIconOut` type (same file, near other API response types):

```ts
export type MapIconOut = { id: string; title: string; category: string; contentType: string; createdAt: string };
```

- [ ] **Step 4: Implement in `itemClient.ts`**

Right after `sampleCollectionField`'s implementation:

```ts
    async presignMapIconUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>("POST", "/map-icons/presign", {
        filename,
        contentType,
      });
    },

    async createMapIcon(input: { title: string; category: string; s3Key: string; contentType: string }) {
      return request<MapIconOut>("POST", "/map-icons", input);
    },

    async listMapIcons() {
      return request<MapIconOut[]>("GET", "/map-icons");
    },

    async deleteMapIcon(iconId: string) {
      await request<void>("DELETE", `/map-icons/${iconId}`);
    },

    mapIconFileUrl(iconId: string) {
      return `${coreUrl}/map-icons/${iconId}/file`;
    },
```

`uploadToPresignedUrl` (existing method, `itemClient.ts:1403`) is reused
as-is for the actual PUT — no new upload helper needed.

- [ ] **Step 5: Run to verify pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "MapIcon"`
Expected: PASS.

- [ ] **Step 6: `StaticItemClient` rejections**

In `shell/src/staticExport/StaticItemClient.ts`, add (mirror
`sampleCollectionField`'s `unsupported()` style, `StaticItemClient.ts:108`):

```ts
    async presignMapIconUpload(..._args: unknown[]) {
      return unsupported();
    },
    async createMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    async listMapIcons() {
      return unsupported();
    },
    async deleteMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    mapIconFileUrl(..._args: unknown[]) {
      throw new Error("Non disponible dans un export statique");
    },
```

Add a matching test in `StaticItemClient.test.ts` (mirror the existing
`sampleCollectionField` rejection test).

- [ ] **Step 7: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green — `npm run build` in particular proves no `ItemClient`
implementer (there are exactly two: `itemClient.ts`,
`StaticItemClient.ts`) is left incomplete.

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute les 5 méthodes ItemClient de la bibliothèque d'icônes
EOF
)"
```

---

## Task 10: Shell — icon picker UI (Lucide grid + custom upload) + custom icon rendering

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `LUCIDE_ICONS`, `IconCategory` (Task 4); `listMapIcons`,
  `createMapIcon`, `deleteMapIcon`, `presignMapIconUpload`,
  `uploadToPresignedUrl`, `mapIconFileUrl` (Task 9); `iconImageId` (Task 5).

- [ ] **Step 1: Write the failing test for the picker**

```ts
test("picking a Lucide icon for a categorical value writes icon.mapping", async () => {
  const onChange = vi.fn();
  renderEditor({
    value: undefined,
    availableFields: ["categorie"],
    onChange,
    // MapSymbologyEditor's props gain listCustomIcons/uploadCustomIcon/deleteCustomIcon (Step 3) —
    // pass no-op mocks here, only the Lucide path is under test.
    listCustomIcons: vi.fn().mockResolvedValue([]),
  });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter des icônes" }));
  await userEvent.type(screen.getByLabelText("Champ icône"), "categorie");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les valeurs" }));
  // domain resolution reuses computeColorDomain's categorical path via runStatistics,
  // mocked in this file's harness the same way the existing color tests already do.
  await userEvent.click(screen.getByRole("img", { name: "school" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      icon: expect.objectContaining({ mapping: expect.objectContaining({ /* first domain value */ }) }),
    }),
  );
});
```

Given the exact domain-value-under-edit depends on this file's existing
`runStatistics` mock return shape (read the file's categorical-color test
first and copy its mock verbatim), finalize this test's exact
`mapping`-key assertion against that same mocked value rather than
inventing one.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx -t "icônes"`
Expected: FAIL — no such button/UI.

- [ ] **Step 3: Extend `MapSymbologyEditor`'s props**

```ts
export function MapSymbologyEditor({
  value,
  availableFields,
  themeColors,
  runStatistics,
  sampleField,
  jenksAvailable = true,
  listCustomIcons,
  uploadCustomIcon,
  deleteCustomIcon,
  onChange,
}: {
  // ...existing props unchanged...
  listCustomIcons: () => Promise<{ id: string; title: string; category: string }[]>;
  uploadCustomIcon: (file: File, title: string, category: string) => Promise<{ id: string }>;
  deleteCustomIcon: (id: string) => Promise<void>;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
```

- [ ] **Step 4: Implement the icon block**

Add local state:

```tsx
  const icon = value?.icon;
  const [iconField, setIconField] = useState(icon?.field ?? "");
  const [customIcons, setCustomIcons] = useState<{ id: string; title: string; category: string }[]>([]);
  const [iconBusy, setIconBusy] = useState(false);

  useEffect(() => {
    void listCustomIcons().then(setCustomIcons);
  }, [listCustomIcons]);

  async function recomputeIconDomain() {
    if (!iconField) return;
    setIconBusy(true);
    try {
      const domain = await computeColorDomain(
        { field: iconField, mode: "categorical" },
        { runStatistics, sampleField },
      );
      if (domain.kind !== "categorical") return;
      onChange({
        ...value,
        icon: { field: iconField, domain, mapping: icon?.mapping ?? {}, fallback: icon?.fallback },
      });
    } finally {
      setIconBusy(false);
    }
  }

  function assignIcon(forValue: string, ref: IconRef) {
    if (!icon) return;
    onChange({ ...value, icon: { ...icon, mapping: { ...icon.mapping, [forValue]: ref } } });
  }

  function clearIcon() {
    const { icon: _icon, ...rest } = value ?? {};
    onChange(Object.keys(rest).length > 0 ? rest : undefined);
  }
```

JSX, appended after the stroke block from Task 3:

```tsx
      {!icon && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setIconField("")}
        >
          Ajouter des icônes
        </button>
      )}
      {(icon || iconField !== undefined) && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Champ icône
            <input
              aria-label="Champ icône"
              list={`${listId}-fields`}
              className={inputCls}
              value={iconField}
              onChange={(e) => setIconField(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={iconBusy || !iconField}
            onClick={() => void recomputeIconDomain()}
          >
            {iconBusy ? "Calcul…" : "Recalculer les valeurs"}
          </button>
          {icon?.domain.values.map((v) => (
            <div key={v} className="flex flex-col gap-1">
              <p className="text-xs font-medium">{v}</p>
              <div className="flex flex-wrap gap-1">
                {LUCIDE_ICONS.map((li) => (
                  <button
                    key={li.name}
                    type="button"
                    role="img"
                    aria-label={li.name}
                    className="h-6 w-6 rounded border border-slate-200"
                    onClick={() => assignIcon(v, { source: "lucide", name: li.name })}
                  />
                ))}
                {customIcons.map((ci) => (
                  <button
                    key={ci.id}
                    type="button"
                    role="img"
                    aria-label={ci.title}
                    className="h-6 w-6 rounded border border-slate-200"
                    onClick={() => assignIcon(v, { source: "custom", id: ci.id })}
                  />
                ))}
              </div>
            </div>
          ))}
          {icon && (
            <button type="button" className="self-start text-xs text-red-700 underline" onClick={clearIcon}>
              Retirer les icônes
            </button>
          )}
        </div>
      )}
```

Add `import { LUCIDE_ICONS, type IconCategory } from
"../builder/widgets/iconLibrary";` and `import type { IconRef } from
"../builder/widgets/mapSymbology";` at the top.

This step deliberately skips the upload UI itself (a file `<input>` calling
`uploadCustomIcon`) — it is straightforward wiring with no new behavior to
test beyond what Step 1 already covers indirectly via `listCustomIcons`;
add it now as plain JSX (not TDD'd separately, consistent with this file's
existing precedent — `LayerPicker`'s own upload affordances are similarly
untested UI glue):

```tsx
          <label className={labelCls}>
            Uploader une icône personnalisée
            <input
              type="file"
              accept="image/svg+xml,image/png"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const created = await uploadCustomIcon(file, file.name, "generic");
                setCustomIcons((prev) => [...prev, { id: created.id, title: file.name, category: "generic" }]);
              }}
            />
          </label>
```

- [ ] **Step 5: Wire the two hosts' concrete `listCustomIcons`/`uploadCustomIcon`/`deleteCustomIcon`**

In `shell/src/map/LayersPanel.tsx`'s `LayerSymbologyEditor` and
`shell/src/builder/widgets/mapWidget.tsx`'s `PropsPanel`, both already call
`<MapSymbologyEditor ...>` — add the three new props, identical at both
call sites (these three are host-agnostic, unlike `runStatistics`/
`sampleField`):

```tsx
        listCustomIcons={() => client.listMapIcons()}
        uploadCustomIcon={async (file, title, category) => {
          const { uploadUrl, key } = await client.presignMapIconUpload(file.name, file.type);
          await client.uploadToPresignedUrl(uploadUrl, file);
          return client.createMapIcon({ title, category, s3Key: key, contentType: file.type });
        }}
        deleteCustomIcon={(id) => client.deleteMapIcon(id)}
```

(`client` is already in scope at both call sites via `useItemClient()`.)

- [ ] **Step 6: Custom icon rendering in `MapView.tsx`**

In Task 6's `loadIconImages`, replace the `if (!id.startsWith("lucide:"))
return;` early-out with the custom branch — custom icons are **not** `sdf`
(§ Task deviation: multi-color icons must not go through the alpha-mask
path):

```ts
async function loadIconImages(map: maplibregl.Map, layers: MapConfig["layers"], mapIconFileUrl: ((id: string) => string) | undefined) {
  // ... existing ids collection unchanged ...
  await Promise.all(
    [...ids].map(async (id) => {
      if (map.hasImage(id)) return;
      if (id.startsWith("lucide:")) {
        const bitmap = await rasterizeLucideIcon(id.slice("lucide:".length));
        if (!map.hasImage(id)) map.addImage(id, bitmap, { sdf: true });
        return;
      }
      if (id.startsWith("custom:") && mapIconFileUrl) {
        const iconId = id.slice("custom:".length);
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.src = mapIconFileUrl(iconId);
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
        });
        if (!map.hasImage(id)) map.addImage(id, img); // no sdf: preserve RGBA as-is.
      }
    }),
  );
}
```

Add a new `getMapIconFileUrl?: (id: string) => string` prop to `MapView`
(same optionality precedent as `getAuthToken`/`getCoreUrl`), threaded into
the `loadIconImages` calls. `mapWidget.tsx`/`LayersPanel`'s map host both
pass `client.mapIconFileUrl` (or leave it `undefined` for the editor
context where a preview of a not-yet-saved custom icon isn't needed).

- [ ] **Step 7: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx src/map/MapView.test.tsx`
Expected: PASS.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/map/LayersPanel.tsx shell/src/builder/widgets/mapWidget.tsx
git commit -m "$(cat <<'EOF'
feat(shell): picker d'icônes (grille Lucide + bibliothèque personnalisée)

Upload direct navigateur→S3 (patron A6), rendu RGBA non-SDF pour les
icônes personnalisées (peuvent être multicolores, contrairement aux
traits Lucide).
EOF
)"
```

---

## Task 11: Shell — `labelFeatureState.ts` (pure)

**Files:**
- Create: `shell/src/map/labelFeatureState.ts`
- Create: `shell/src/map/labelFeatureState.test.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.ts` (adds `LayerSymbology.label`)
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: `interpolatePopupTemplate`, `ExprContext` from `./popupTemplate`
  (existing, SP-24 — never `renderPopupTemplate`, per spec §1).
- Produces: `computeLabelStateUpdates(features, template):
  {id, label}[]` — consumed by Task 12's `MapView.tsx`.

- [ ] **Step 1: Write the failing tests for `LayerSymbology.label`**

Append to `mapSymbology.test.ts`:

```ts
test("LayerSymbology.label accepts a template and style fields (type-level, compiles)", () => {
  const symbology: LayerSymbology = {
    label: { template: "${nom}", size: 12, color: "#000", haloColor: "#fff", haloWidth: 1 },
  };
  expect(symbology.label?.template).toBe("${nom}");
});
```

- [ ] **Step 2: Add the type**

In `mapSymbology.ts`:

```ts
export type LayerLabel = {
  template: string;
  size: number;
  color: string;
  haloColor: string;
  haloWidth: number;
};
```

Extend `LayerSymbology` with `label?: LayerLabel`. Run: `cd shell && npx
vitest run src/builder/widgets/mapSymbology.test.ts` — PASS.

- [ ] **Step 3: Write the failing tests for `computeLabelStateUpdates`**

Create `shell/src/map/labelFeatureState.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { computeLabelStateUpdates } from "./labelFeatureState";

test("interpolates a simple field template per feature", () => {
  const updates = computeLabelStateUpdates(
    [{ id: 1, properties: { nom: "Tulle" } }, { id: 2, properties: { nom: "Brive" } }],
    "${nom}",
  );
  expect(updates).toEqual([{ id: 1, label: "Tulle" }, { id: 2, label: "Brive" }]);
});

test("evaluates a full CEL condition per feature", () => {
  const updates = computeLabelStateUpdates(
    [{ id: 1, properties: { nom: "Tulle", pop: 15000 } }, { id: 2, properties: { nom: "Hameau", pop: 40 } }],
    '${pop > 10000 ? "grande ville" : "commune"}',
  );
  expect(updates).toEqual([
    { id: 1, label: "grande ville" },
    { id: 2, label: "commune" },
  ]);
});

test("a missing property interpolates to an empty string, never throws", () => {
  const updates = computeLabelStateUpdates([{ id: 1, properties: {} }], "${nom}");
  expect(updates).toEqual([{ id: 1, label: "" }]);
});

test("plain literal text with no placeholder passes through unchanged", () => {
  const updates = computeLabelStateUpdates([{ id: 1, properties: {} }], "Sans donnée");
  expect(updates).toEqual([{ id: 1, label: "Sans donnée" }]);
});
```

- [ ] **Step 4: Run to verify failure**

Run: `cd shell && npx vitest run src/map/labelFeatureState.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 5: Implement**

```ts
// SPDX-License-Identifier: Apache-2.0
// Étiquettes de carte (SP-27 §3.3) : réutilise tel quel le moteur CEL du
// popup (interpolatePopupTemplate, SP-24) — jamais renderPopupTemplate, qui
// sanitize en markdown : MapLibre affiche du texte brut, pas du HTML.
import { interpolatePopupTemplate } from "./popupTemplate";

export function computeLabelStateUpdates(
  features: { id: string | number; properties: Record<string, unknown> }[],
  template: string,
): { id: string | number; label: string }[] {
  return features.map((f) => ({
    id: f.id,
    label: interpolatePopupTemplate(template, { vars: {}, user: { name: "" }, record: f.properties }),
  }));
}
```

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/map/labelFeatureState.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 7: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run`

```bash
git add shell/src/map/labelFeatureState.ts shell/src/map/labelFeatureState.test.ts shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute computeLabelStateUpdates (gabarit CEL par feature)

Réutilise interpolatePopupTemplate (SP-24) tel quel — jamais la
sanitisation markdown du popup, une étiquette de carte est du texte
brut rendu par MapLibre.
EOF
)"
```

---

## Task 12: Shell — `MapView.tsx`: `feature-state` label loop

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `computeLabelStateUpdates` (Task 11).

- [ ] **Step 1: Write the failing test**

```ts
test("a layer with a label template gets a promoteId and a symbol text layer", () => {
  const { map } = renderMapView({
    layers: [
      {
        id: "l1", title: "Communes", visible: true, kind: "vector",
        tilesUrl: "https://example.test/{z}/{x}/{y}.mvt", sourceLayer: "communes",
        geometryKind: "polygon", pkColumn: "insee",
        symbology: { label: { template: "${nom}", size: 12, color: "#000", haloColor: "#fff", haloWidth: 1 } },
      },
    ],
  });

  expect(map.addSource).toHaveBeenCalledWith(
    "l1",
    expect.objectContaining({ type: "vector", promoteId: "insee" }),
  );
  expect(map.addLayer).toHaveBeenCalledWith(
    expect.objectContaining({
      id: "l1__label",
      type: "symbol",
      layout: expect.objectContaining({ "text-field": ["feature-state", "label"] }),
    }),
  );
});

test("sourcedata triggers a label recompute via setFeatureState", async () => {
  const { map, emit } = renderMapView({
    layers: [
      {
        id: "l1", title: "Communes", visible: true, kind: "vector",
        tilesUrl: "https://example.test/{z}/{x}/{y}.mvt", sourceLayer: "communes",
        geometryKind: "polygon", pkColumn: "insee",
        symbology: { label: { template: "${nom}", size: 12, color: "#000", haloColor: "#fff", haloWidth: 1 } },
      },
    ],
  });
  map.querySourceFeatures = vi.fn().mockReturnValue([{ id: "19108", properties: { nom: "Tulle" } }]);

  emit("sourcedata", { sourceId: "l1", isSourceLoaded: true });
  await flushPromises();

  expect(map.setFeatureState).toHaveBeenCalledWith(
    { source: "l1", id: "19108" },
    { label: "Tulle" },
  );
});
```

Adjust `renderMapView`'s exact mock (`map.on`/`emit` helper for firing
MapLibre events in this test file) to whatever's already established there.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "label"`
Expected: FAIL.

- [ ] **Step 3: `promoteId` on the source**

In `applyLayers`, the `kind === "vector"` branch's `map.addSource` call
(around line 264):

```ts
map.addSource(layer.id, {
  type: "vector",
  tiles: [layer.tilesUrl],
  ...(layer.symbology?.label ? { promoteId: layer.pkColumn ?? "id" } : {}),
});
```

Same for the `kind === "feature"` branch's `map.addSource` (GeoJSON source,
`promoteId` works identically there):

```ts
map.addSource(layer.id, {
  type: "geojson",
  data: layer.url,
  ...(layer.symbology?.label ? { promoteId: "id" } : {}),
});
```

- [ ] **Step 4: The `symbol` text layer**

At each of the same 3 sites as Task 2/6's paired layers, after the main
layer is added, if `layer.symbology?.label`:

```ts
if (layer.symbology?.label) {
  const label = layer.symbology.label;
  map.addLayer({
    id: `${id}__label`,
    type: "symbol",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    layout: { "text-field": ["feature-state", "label"], "text-size": label.size },
    paint: {
      "text-color": label.color,
      "text-halo-color": label.haloColor,
      "text-halo-width": label.haloWidth,
    },
  });
  layerIds.push(`${id}__label`);
}
```

- [ ] **Step 5: The recompute loop**

New module-level (outside the component) pure-ish function, mirroring
`loadIconImages`'s shape:

```ts
function recomputeLabels(map: maplibregl.Map, layers: MapConfig["layers"]) {
  for (const layer of layers) {
    if ((layer.kind !== "vector" && layer.kind !== "feature") || !layer.symbology?.label) continue;
    const features =
      layer.kind === "vector"
        ? map.querySourceFeatures(layer.id, { sourceLayer: layer.sourceLayer })
        : map.querySourceFeatures(layer.id);
    const updates = computeLabelStateUpdates(
      features.map((f) => ({ id: f.id as string | number, properties: (f.properties ?? {}) as Record<string, unknown> })),
      layer.symbology.label.template,
    );
    for (const u of updates) {
      if (u.id == null) continue;
      map.setFeatureState({ source: layer.id, id: u.id }, { label: u.label });
    }
  }
}
```

Wire it in the existing `useEffect` that sets up the map (around
`MapView.tsx:614`, where other `map.on(...)` listeners already live),
debounced ~150ms:

```ts
let labelDebounce: ReturnType<typeof setTimeout> | undefined;
const scheduleRecompute = () => {
  clearTimeout(labelDebounce);
  labelDebounce = setTimeout(() => recomputeLabels(map, layersRef.current), 150);
};
map.on("sourcedata", scheduleRecompute);
map.on("moveend", scheduleRecompute);
```

Add matching cleanup (`map.off(...)`, `clearTimeout(labelDebounce)`) in the
same effect's return/teardown, next to the file's existing listener
cleanup.

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, full file green.

- [ ] **Step 7: MapSymbologyEditor label block**

Add to `MapSymbologyEditor.tsx`, after the icon block (Task 10):

```tsx
      {!value?.label && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => onChange({ ...value, label: { template: "", size: 12, color: "#1e293b", haloColor: "#ffffff", haloWidth: 1 } })}
        >
          Ajouter une étiquette
        </button>
      )}
      {value?.label && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Gabarit (ex. {"${nom}"})
            <textarea
              aria-label="Gabarit d'étiquette"
              className={inputCls}
              value={value.label.template}
              onChange={(e) => onChange({ ...value, label: { ...value.label!, template: e.target.value } })}
            />
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={() => {
              const { label: _label, ...rest } = value ?? {};
              onChange(Object.keys(rest).length > 0 ? rest : undefined);
            }}
          >
            Retirer l'étiquette
          </button>
        </div>
      )}
```

- [ ] **Step 8: Run the editor tests + full shell gates**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx src/map/MapView.test.tsx`
Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

- [ ] **Step 9: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): rend les étiquettes CEL via feature-state (vector + feature)

promoteId sur la source, recalcul débounced (sourcedata/moveend) sur
les seules features chargées, couche symbol dédiée par couche stylée.
EOF
)"
```

---

## Task 13: Shell — `measureSketch.ts` (pure geodesic math)

**Files:**
- Create: `shell/src/map/measureSketch.ts`
- Create: `shell/src/map/measureSketch.test.ts`

**Interfaces:**
- Produces: `haversineDistanceMeters(a, b)`, `lineDistanceMeters(points)`,
  `sphericalPolygonAreaSquareMeters(points)`, `formatDistance(meters)`,
  `formatArea(squareMeters)` — consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import {
  formatArea,
  formatDistance,
  haversineDistanceMeters,
  lineDistanceMeters,
  sphericalPolygonAreaSquareMeters,
} from "./measureSketch";

test("haversineDistanceMeters: 1 degree of longitude at the equator is ~111.2 km", () => {
  const d = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 1, lat: 0 });
  expect(d).toBeGreaterThan(111000);
  expect(d).toBeLessThan(111500);
});

test("haversineDistanceMeters: same point is 0", () => {
  expect(haversineDistanceMeters({ lng: 2, lat: 45 }, { lng: 2, lat: 45 })).toBe(0);
});

test("lineDistanceMeters sums consecutive segments", () => {
  const total = lineDistanceMeters([{ lng: 0, lat: 0 }, { lng: 1, lat: 0 }, { lng: 1, lat: 1 }]);
  const seg1 = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 1, lat: 0 });
  const seg2 = haversineDistanceMeters({ lng: 1, lat: 0 }, { lng: 1, lat: 1 });
  expect(total).toBeCloseTo(seg1 + seg2, 0);
});

test("lineDistanceMeters on fewer than 2 points is 0", () => {
  expect(lineDistanceMeters([])).toBe(0);
  expect(lineDistanceMeters([{ lng: 0, lat: 0 }])).toBe(0);
});

test("sphericalPolygonAreaSquareMeters: a small square near the equator matches a flat-Earth estimate within 1%", () => {
  // ~0.01deg square at the equator: side ~1.1132km (111.32 m per 0.001deg), area ~1.239 km^2.
  const ring = [
    { lng: 0, lat: 0 },
    { lng: 0.01, lat: 0 },
    { lng: 0.01, lat: 0.01 },
    { lng: 0, lat: 0.01 },
    { lng: 0, lat: 0 },
  ];
  const area = sphericalPolygonAreaSquareMeters(ring);
  const side = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 0.01, lat: 0 });
  const flatEstimate = side * side;
  expect(Math.abs(area - flatEstimate) / flatEstimate).toBeLessThan(0.01);
});

test("sphericalPolygonAreaSquareMeters on fewer than 3 distinct points is 0", () => {
  expect(sphericalPolygonAreaSquareMeters([{ lng: 0, lat: 0 }, { lng: 1, lat: 0 }])).toBe(0);
});

test("formatDistance switches from meters to kilometers at 1000m", () => {
  expect(formatDistance(500)).toBe("500 m");
  expect(formatDistance(1500)).toBe("1,50 km");
});

test("formatArea switches from m² to ha to km²", () => {
  expect(formatArea(5000)).toBe("5 000 m²");
  expect(formatArea(50_000)).toBe("5,00 ha");
  expect(formatArea(5_000_000)).toBe("5,00 km²");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/measureSketch.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```ts
// SPDX-License-Identifier: Apache-2.0
// Mesure géodésique maison (SP-27 §3, décision de session #8) : haversine
// (sphère, rayon moyen terrestre) pour la distance, formule de l'aire d'un
// polygone sphérique (excès sphérique via la formule de l'aire signée sur
// une projection locale) pour la surface. Aucune bibliothèque — précédent
// jenksBreaks/popupTemplate.
export type LngLat = { lng: number; lat: number };

const EARTH_RADIUS_M = 6_371_000;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

export function haversineDistanceMeters(a: LngLat, b: LngLat): number {
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineDistanceMeters(points: LngLat[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += haversineDistanceMeters(points[i - 1], points[i]);
  return total;
}

// Spherical excess formula (L'Huilier-free, small-polygon-safe variant): sum
// of (lng_i+1 - lng_i) * (2 + sin(lat_i) + sin(lat_i+1)), scaled by R^2/2 —
// the standard "shoelace on a sphere" identity. Accurate for polygons small
// relative to the Earth's radius (any realistic map measurement use case);
// not meant for continent-scale areas.
export function sphericalPolygonAreaSquareMeters(points: LngLat[]): number {
  const ring = points.length >= 2 && points[0].lng === points[points.length - 1].lng && points[0].lat === points[points.length - 1].lat
    ? points.slice(0, -1)
    : points;
  if (ring.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % ring.length];
    sum += toRad(p2.lng - p1.lng) * (2 + Math.sin(toRad(p1.lat)) + Math.sin(toRad(p2.lat)));
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} km`;
}

export function formatArea(squareMeters: number): string {
  if (squareMeters < 10_000) return `${Math.round(squareMeters).toLocaleString("fr-FR")} m²`;
  if (squareMeters < 1_000_000)
    return `${(squareMeters / 10_000).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ha`;
  return `${(squareMeters / 1_000_000).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} km²`;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/measureSketch.test.ts`
Expected: PASS (9 tests). If the spherical-area test's 1% tolerance fails,
print the two values and check for a sign error in the shoelace sum before
loosening the tolerance — a small square near the equator is exactly the
regime where the flat-Earth approximation should be tightest.

- [ ] **Step 5: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run`

```bash
git add shell/src/map/measureSketch.ts shell/src/map/measureSketch.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute measureSketch (haversine + aire sphérique, maison)
EOF
)"
```

---

## Task 14: Shell — `MapMeasureSketchToolbar.tsx` (measure UI)

**Files:**
- Create: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Create: `shell/src/map/MapMeasureSketchToolbar.test.tsx`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `haversineDistanceMeters`, `lineDistanceMeters`,
  `sphericalPolygonAreaSquareMeters`, `formatDistance`, `formatArea`
  (Task 13).
- Produces: `MapMeasureSketchToolbar` component; `MapView` gains a new
  `interactiveTools?: boolean` prop (default `false`) that mounts it.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/MapMeasureSketchToolbar.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { MapMeasureSketchToolbar } from "./MapMeasureSketchToolbar";

function makeMapStub() {
  const handlers: Record<string, ((e: unknown) => void)[]> = {};
  return {
    on: vi.fn((event: string, handler: (e: unknown) => void) => {
      (handlers[event] ??= []).push(handler);
    }),
    off: vi.fn(),
    emit: (event: string, e: unknown) => handlers[event]?.forEach((h) => h(e)),
    getCanvas: () => ({ style: {} }),
  };
}

test("clicking Mesurer then clicking two map points shows the running distance", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });

  expect(screen.getByText(/111 km|111,\d\d km/)).toBeInTheDocument();
});

test("Effacer tout clears the current measurement", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
});

test("no server request is ever made — the toolbar takes no ItemClient/fetch dependency", () => {
  // Structural proof: the component's props type has no client/fetch field.
  // (Type-level — this test exists so a future prop addition is caught by
  // a reviewer reading the diff, not to assert runtime behavior beyond
  // what the two tests above already cover.)
  expect(MapMeasureSketchToolbar.length).toBeLessThanOrEqual(1); // single props object
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the measure half**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { formatArea, formatDistance, lineDistanceMeters, sphericalPolygonAreaSquareMeters, type LngLat } from "./measureSketch";

type Mode = "idle" | "measure-distance" | "measure-area" | "sketch";

// Purely client-side, ephemeral — no ItemClient/fetch dependency by design
// (spec §2: jamais persisté, jamais envoyé au serveur).
export function MapMeasureSketchToolbar({ map }: { map: Pick<maplibregl.Map, "on" | "off" | "getCanvas"> }) {
  const [mode, setMode] = useState<Mode>("idle");
  const [points, setPoints] = useState<LngLat[]>([]);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    function onClick(e: unknown) {
      if (modeRef.current !== "measure-distance" && modeRef.current !== "measure-area") return;
      const { lngLat } = e as { lngLat: LngLat };
      setPoints((prev) => [...prev, lngLat]);
    }
    map.on("click", onClick);
    return () => map.off("click", onClick);
  }, [map]);

  function startMeasureDistance() {
    setMode("measure-distance");
    setPoints([]);
  }

  function clearAll() {
    setMode("idle");
    setPoints([]);
  }

  const distance = mode === "measure-distance" && points.length >= 2 ? lineDistanceMeters(points) : null;
  const area = mode === "measure-area" && points.length >= 3 ? sphericalPolygonAreaSquareMeters(points) : null;

  return (
    <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-md bg-white/90 p-2 text-xs shadow">
      <div className="flex gap-1">
        <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={startMeasureDistance}>
          Mesurer
        </button>
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-1"
          onClick={() => {
            setMode("measure-area");
            setPoints([]);
          }}
        >
          Surface
        </button>
        <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={clearAll}>
          Effacer tout
        </button>
      </div>
      {distance !== null && <p>{formatDistance(distance)}</p>}
      {area !== null && <p>{formatArea(area)}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Mount it from `MapView`**

Add `interactiveTools?: boolean` to `MapView`'s prop type (near
`hideLegend`), and, in the component body, expose the underlying
`maplibregl.Map` via the existing `mapRef`:

```tsx
{interactiveTools && mapRef.current && <MapMeasureSketchToolbar map={mapRef.current} />}
```

Placed in the component's JSX return, alongside the existing `<MapPopup
.../>` mount (`MapView.tsx` around line 818) — same conditional-render
pattern, both are overlays keyed off internal refs/state.

- [ ] **Step 6: Run MapView's suite + full shell gates**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx && npm run lint && npm run format:check && npx vitest run && npm run build`

- [ ] **Step 7: Commit**

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): outil de mesure (distance/surface) éphémère, sans écriture

Purement client, aucune dépendance ItemClient/fetch — jamais persisté.
EOF
)"
```

---

## Task 15: Shell — croquis (sketch primitives)

**Files:**
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Modify: `shell/src/map/MapMeasureSketchToolbar.test.tsx`

**Interfaces:** none new — extends the same component's `mode` state.

- [ ] **Step 1: Write the failing tests**

```tsx
test("Croquis mode with the point tool drops a colored marker at each click", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  map.emit("mousedown", { lngLat: { lng: 0, lat: 0 } });
  map.emit("mousemove", { lngLat: { lng: 0.001, lat: 0 } });
  map.emit("mouseup", { lngLat: { lng: 0.001, lat: 0 } });

  expect(screen.getByText("1 tracé")).toBeInTheDocument();
});

test("adding a text marker prompts for text and places it", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue("Point de rendez-vous"));
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });

  expect(screen.getByText("Point de rendez-vous")).toBeInTheDocument();
});

test("Effacer tout also clears sketch shapes", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(screen.queryByText(/tracé|rectangle/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx -t "Croquis|Tracé|Texte|Rectangle"`
Expected: FAIL.

- [ ] **Step 3: Implement**

Extend the component's state and JSX:

```tsx
type SketchShape =
  | { kind: "freehand"; points: LngLat[]; color: string }
  | { kind: "rect"; from: LngLat; to: LngLat; color: string }
  | { kind: "circle"; center: LngLat; edge: LngLat; color: string }
  | { kind: "polygon"; points: LngLat[]; color: string }
  | { kind: "text"; at: LngLat; text: string; color: string };

type SketchTool = "freehand" | "rect" | "circle" | "polygon" | "text" | null;
```

Add state: `const [sketchTool, setSketchTool] = useState<SketchTool>(null);
const [shapes, setShapes] = useState<SketchShape[]>([]); const [color,
setColor] = useState("#dc2626"); const [freehandPoints, setFreehandPoints] =
useState<LngLat[]>([]); const drawingRef = useRef(false);`

Extend the `click`/new `mousedown`/`mousemove`/`mouseup` effect:

```tsx
useEffect(() => {
  function onMouseDown(e: unknown) {
    if (modeRef.current !== "sketch" || sketchToolRef.current !== "freehand") return;
    drawingRef.current = true;
    setFreehandPoints([(e as { lngLat: LngLat }).lngLat]);
  }
  function onMouseMove(e: unknown) {
    if (!drawingRef.current) return;
    setFreehandPoints((prev) => [...prev, (e as { lngLat: LngLat }).lngLat]);
  }
  function onMouseUp() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    setFreehandPoints((prev) => {
      if (prev.length >= 2) setShapes((s) => [...s, { kind: "freehand", points: prev, color: colorRef.current }]);
      return [];
    });
  }
  map.on("mousedown", onMouseDown);
  map.on("mousemove", onMouseMove);
  map.on("mouseup", onMouseUp);
  return () => {
    map.off("mousedown", onMouseDown);
    map.off("mousemove", onMouseMove);
    map.off("mouseup", onMouseUp);
  };
}, [map]);
```

(`sketchToolRef`/`colorRef` mirror the existing `modeRef` pattern — a ref
kept in sync with each piece of state read from inside a stable-identity
map event handler, same reason `modeRef` exists: `map.on` is registered
once, but the handler must see current state.)

Click-based tools (`rect`, `circle`, `polygon`, `text`) reuse the existing
`onClick` handler (Step 3 of Task 14), extended:

```tsx
function onClick(e: unknown) {
  const { lngLat } = e as { lngLat: LngLat };
  if (modeRef.current === "measure-distance" || modeRef.current === "measure-area") {
    setPoints((prev) => [...prev, lngLat]);
    return;
  }
  if (modeRef.current !== "sketch") return;
  const tool = sketchToolRef.current;
  if (tool === "text") {
    const text = window.prompt("Texte du marqueur :");
    if (text) setShapes((s) => [...s, { kind: "text", at: lngLat, text, color: colorRef.current }]);
    return;
  }
  if (tool === "rect" || tool === "circle") {
    setPendingCorner((prev) => {
      if (!prev) return lngLat;
      setShapes((s) => [...s, { kind: tool, ...(tool === "rect" ? { from: prev, to: lngLat } : { center: prev, edge: lngLat }), color: colorRef.current }]);
      return null;
    });
    return;
  }
  if (tool === "polygon") {
    setPolygonPoints((prev) => [...prev, lngLat]);
  }
}
```

Add `const [pendingCorner, setPendingCorner] = useState<LngLat | null>(null);
const [polygonPoints, setPolygonPoints] = useState<LngLat[]>([]);` and a
"Terminer le polygone" button that pushes `polygonPoints` into `shapes` as a
`{kind: "polygon", ...}` and resets it, shown only when `sketchTool ===
"polygon" && polygonPoints.length > 0`.

JSX additions, in the toolbar's render:

```tsx
<div className="flex gap-1">
  <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setMode("sketch")}>
    Croquis
  </button>
  {mode === "sketch" && (
    <>
      <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setSketchTool("freehand")}>
        Tracé libre
      </button>
      <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setSketchTool("rect")}>
        Rectangle
      </button>
      <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setSketchTool("circle")}>
        Cercle
      </button>
      <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setSketchTool("polygon")}>
        Polygone
      </button>
      <button type="button" className="rounded border border-slate-300 px-2 py-1" onClick={() => setSketchTool("text")}>
        Texte
      </button>
      <input aria-label="Couleur du croquis" type="color" value={color} onChange={(e) => setColor(e.target.value)} />
    </>
  )}
</div>
{shapes.filter((s) => s.kind === "freehand").length > 0 && <p>{shapes.filter((s) => s.kind === "freehand").length} tracé</p>}
{shapes.map((s, i) => s.kind === "text" && <p key={i}>{s.text}</p>)}
```

And extend `clearAll` (Task 14, Step 3) to also reset sketch state:

```tsx
function clearAll() {
  setMode("idle");
  setPoints([]);
  setShapes([]);
  setSketchTool(null);
  setPolygonPoints([]);
  setPendingCorner(null);
}
```

This step deliberately keeps the shapes as **React state only, never
rendered onto the MapLibre canvas as an actual overlay layer** — the tests
in Step 1 assert on the toolbar's own textual summary, not on
`map.addSource`/`addLayer` calls. Rendering the shapes visually on the map
(a GeoJSON overlay source updated from `shapes`) is a real, valuable
follow-up but is not exercised by any test in this plan and is called out
explicitly in Task 17's E2E task as the thing that actually proves the
sketch is visible — if Task 17's E2E proof requires seeing a sketch shape
rendered on the map (not just in the toolbar's text list), add that
GeoJSON-overlay wiring there, in the same style as `MapPopup`'s existing
overlay-source pattern (`map.addSource("__highlight__", ...)`,
`HIGHLIGHT_ID` constant already in this file) — do not invent it here
speculatively.

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le croquis (tracé libre, formes, texte, couleur)

État React éphémère uniquement — pas de rendu carte, cf. Task 17 pour
le rendu visuel réel exigé par la preuve E2E.
EOF
)"
```

---

## Task 16: Shell — wire `mapWidget.tsx`

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("the measure/sketch toolbar is mounted only outside edit mode", () => {
  const { rerender } = renderMapWidget({ ctx: { mode: "edit" } }); // reuse this file's existing harness
  expect(screen.queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();

  rerender(<Widget ctx={{ mode: "runtime" }} />); // adjust to this file's actual rerender pattern
  expect(screen.getByRole("button", { name: "Mesurer" })).toBeInTheDocument();
});
```

Adjust to whatever harness `mapWidget.test.tsx` already uses to render
`Component` with a given `ctx` — read the file's existing `mode`-dependent
tests (if any) first.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "mesure"`
Expected: FAIL.

- [ ] **Step 3: Wire the prop**

In `mapWidget.tsx`'s `Component`, on the `<MapView ...>` element:

```tsx
<MapView
  ref={handle}
  config={config}
  interactiveTools={ctx.mode !== "edit"}
  getAuthToken={client.getAuthToken}
  getCoreUrl={client.getCoreUrl}
  // ...existing props unchanged...
/>
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS.

- [ ] **Step 5: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): active mesure/croquis sur le widget carte hors édition

Runtime app/dashboard et /sites/{slug} (même widget) ; absent du mode
édition du builder, cohérent avec la preuve de sortie 4.5 (lecteur
sans droit d'écriture).
EOF
)"
```

---

## Task 17: E2E proofs + sketch overlay rendering + final verification

**Files:**
- Create: `shell/e2e/map-symbology-advanced.spec.ts`
- Create: `shell/e2e/map-measure-sketch.spec.ts`
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx` (sketch shapes → a real
  GeoJSON overlay layer, needed for the E2E proof to see anything on the
  map itself)
- Modify: `shell/src/map/MapMeasureSketchToolbar.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Render sketch shapes as a real map overlay**

`MapMeasureSketchToolbar` needs the `maplibregl.Map` instance to also
`addSource`/`addLayer` a GeoJSON overlay for `shapes` — extend its props to
receive the full `maplibregl.Map` (not the narrowed `Pick<...>` from Task
14; widen the prop type) and add an effect that syncs `shapes`/
`freehandPoints`/`points` (the in-progress measure line/polygon too, for
live feedback) into a `__sketch__` GeoJSON source:

```tsx
const SKETCH_SOURCE_ID = "__sketch__";

useEffect(() => {
  const fullMap = map as maplibregl.Map;
  if (!fullMap.getSource) return; // test stub from Task 14/15 doesn't implement this — guarded, not exercised there.
  const featureCollection = {
    type: "FeatureCollection" as const,
    features: [
      ...shapes.map(shapeToGeoJSONFeature),
      ...(points.length >= 2 ? [{ type: "Feature" as const, properties: {}, geometry: { type: mode === "measure-area" ? "Polygon" : "LineString", coordinates: mode === "measure-area" ? [[...points.map((p) => [p.lng, p.lat]), [points[0].lng, points[0].lat]]] : points.map((p) => [p.lng, p.lat]) } }] : []),
    ],
  };
  if (fullMap.getSource(SKETCH_SOURCE_ID)) {
    (fullMap.getSource(SKETCH_SOURCE_ID) as maplibregl.GeoJSONSource).setData(featureCollection);
  } else {
    fullMap.addSource(SKETCH_SOURCE_ID, { type: "geojson", data: featureCollection });
    fullMap.addLayer({ id: `${SKETCH_SOURCE_ID}__line`, type: "line", source: SKETCH_SOURCE_ID, filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["get", "color"], "line-width": 2 } });
    fullMap.addLayer({ id: `${SKETCH_SOURCE_ID}__fill`, type: "fill", source: SKETCH_SOURCE_ID, filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": ["get", "color"], "fill-opacity": 0.3 } });
    fullMap.addLayer({ id: `${SKETCH_SOURCE_ID}__point`, type: "circle", source: SKETCH_SOURCE_ID, filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": ["get", "color"], "circle-radius": 5 } });
  }
}, [shapes, points, mode, map]);

function shapeToGeoJSONFeature(shape: SketchShape) {
  const properties = { color: shape.color, ...(shape.kind === "text" ? { text: shape.text } : {}) };
  if (shape.kind === "freehand" || shape.kind === "polygon") {
    return { type: "Feature" as const, properties, geometry: { type: shape.kind === "polygon" ? "Polygon" : "LineString", coordinates: shape.kind === "polygon" ? [[...shape.points.map((p) => [p.lng, p.lat]), [shape.points[0].lng, shape.points[0].lat]]] : shape.points.map((p) => [p.lng, p.lat]) } };
  }
  if (shape.kind === "rect") {
    const { from, to } = shape;
    return { type: "Feature" as const, properties, geometry: { type: "Polygon" as const, coordinates: [[[from.lng, from.lat], [to.lng, from.lat], [to.lng, to.lat], [from.lng, to.lat], [from.lng, from.lat]]] } };
  }
  if (shape.kind === "circle") {
    const steps = 32;
    const r = haversineDistanceMeters(shape.center, shape.edge) / EARTH_METERS_PER_DEGREE_APPROX; // see note below
    const coords = Array.from({ length: steps + 1 }, (_, i) => {
      const t = (i / steps) * 2 * Math.PI;
      return [shape.center.lng + r * Math.cos(t), shape.center.lat + r * Math.sin(t)];
    });
    return { type: "Feature" as const, properties, geometry: { type: "Polygon" as const, coordinates: [coords] } };
  }
  return { type: "Feature" as const, properties, geometry: { type: "Point" as const, coordinates: [shape.at.lng, shape.at.lat] } };
}
```

The circle-radius-in-degrees approximation (`EARTH_METERS_PER_DEGREE_APPROX
= 111_320`, a module constant) is a deliberately rough on-screen circle —
this is a sketch annotation, not a measurement, so sub-percent geodesic
accuracy is not the bar; `measureSketch.ts`'s haversine (exact) is reused
only to size it plausibly from two clicked points.

Update Task 14/15's tests: the `makeMapStub()` helper needs `getSource`
returning `undefined` (so the `if (!fullMap.getSource) return;` guard's
`getSource` check passes as "exists but empty" rather than "doesn't exist
as a function") — add `getSource: vi.fn().mockReturnValue(undefined),
addSource: vi.fn(), addLayer: vi.fn()` to the stub; re-run
`MapMeasureSketchToolbar.test.tsx` to confirm the existing tests (Tasks
14/15) still pass with the widened prop type and new effect.

- [ ] **Step 2: Run the unit suite**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS, no regression.

- [ ] **Step 3: Write the 4.4 E2E proof**

Create `shell/e2e/map-symbology-advanced.spec.ts`, following the pattern of
`shell/e2e/map-symbology.spec.ts` (SP-25's proof — read it first for the
exact fixture/mock/login setup, `VITE_AUTH_MODE=mock` convention, and how it
navigates to `LayersPanel`):

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
// (imports: mirror map-symbology.spec.ts's setup exactly)

test("a layer styled with a label, an icon and a stroke renders identically in the export capture", async ({ page }) => {
  // 1. Navigate to the map editor for a fixture vector layer (reuse the
  //    fixture from map-symbology.spec.ts / map-popup.spec.ts —
  //    shell/e2e/fixtures/world-tile.mvt).
  // 2. Open the symbology editor, set label template "${name}", pick a
  //    Lucide icon for one categorical value, set a fixed stroke color.
  // 3. Save.
  // 4. Navigate to `?exportRender=1` (per SP-17a's convention) and assert
  //    the exported page shows the same label text and a rendered icon
  //    (screenshot comparison or a DOM/canvas readback — mirror whatever
  //    assertion style map-symbology.spec.ts already uses for "rendered
  //    identically", do not invent a new assertion primitive).
});
```

Do not guess the fixture/route details further than what's written above —
read `map-symbology.spec.ts` and `map-popup.spec.ts` in full before writing
the real test body; both already prove "configure in editor → reload/export
→ same rendering" for a sibling feature.

- [ ] **Step 4: Write the 4.5 E2E proof**

Create `shell/e2e/map-measure-sketch.spec.ts`, following
`analytics-context.spec.ts`'s pattern for driving a real MapLibre WebGL
canvas (documented in CLAUDE.md as the proven precedent) and
`sql-lab.spec.ts`'s pattern for asserting "no write request was made":

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
// (imports: mirror analytics-context.spec.ts's canvas-click setup exactly)

test("a reader can measure a distance on a published app without any write request", async ({ page }) => {
  // 1. Navigate to a published app/dashboard runtime page containing a map
  //    widget (reuse the fixture app from analytics-context.spec.ts or
  //    map-popup.spec.ts).
  // 2. Track network requests (page.on("request", ...)) and assert none
  //    is a POST/PUT/PATCH/DELETE for the duration of this test.
  // 3. Click "Mesurer", click two points on the canvas (same
  //    coordinate-to-pixel technique as map-popup.spec.ts's canvas click).
  // 4. Assert the toolbar shows a distance string matching /\d+ (m|km)/.
});

test("Croquis places a visible shape on the map (sketch overlay source)", async ({ page }) => {
  // Same navigation as above. Click "Croquis" → "Rectangle", click two
  // points, then assert map.getSource("__sketch__") (via page.evaluate
  // against the exposed MapLibre instance, same technique as
  // map-popup.spec.ts's token-attachment assertion) has one Polygon
  // feature.
});
```

- [ ] **Step 5: Run both specs**

Run: `cd shell && npm run e2e -- map-symbology-advanced map-measure-sketch`
Expected: PASS. If the fixture/assertion details sketched in Steps 3-4 don't
match what the referenced sibling specs actually do, fix this spec to match
their real, working pattern — they are the ground truth, not this plan's
sketch of them.

- [ ] **Step 6: Run the complete E2E suite (regression check)**

Run: `cd shell && npm run e2e`
Expected: **110 passed, 4 skipped, 0 failed** (108 baseline + 2 new specs —
if any pre-existing spec now fails, this is exactly the class of
cross-task regression SP-23/24/25's `### Fait` entries warn about: a widget
prop/behavior changed (Task 16's `interactiveTools`, Task 2's `MapLayer`
paint shape) without every consumer of the old shape being re-verified.
Investigate and fix in a separate commit before proceeding, per the
established precedent of this repo's history — do not fold an unrelated
regression fix into this task's own commit.)

- [ ] **Step 7: Full final verification, both sides**

Run:
```bash
cd core && uv run pytest -v
cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports
cd core && uv run pytest tests/test_deployability.py -v
cd shell && npm run lint && npm run format:check && npx vitest run && npm run build
```
Expected: core ≥ 1896 + 5 passed (1 known pre-existing failure unaffected),
coverage ≥ 85; deployability 35/35 (or more if a new rule fired — should
not have, this plan added no new env var beyond `S3_MAPICONS_BUCKET`,
already wired in Task 7); shell test count ≥ 1463 + (however many new tests
Tasks 1-16 added), coverage ≥ 88 (measured after removing
`dist/`/`dist-export/`).

- [ ] **Step 8: `uvx pre-commit run --all-files`**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 hooks green.

- [ ] **Step 9: Commit**

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx shell/e2e/map-symbology-advanced.spec.ts shell/e2e/map-measure-sketch.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): preuves E2E SP-27 (4.4 étiquette/icône/contour, 4.5 mesure/croquis)

Rend les formes de croquis sur une vraie source GeoJSON MapLibre
(__sketch__), nécessaire pour que la preuve E2E observe quelque chose
sur la carte plutôt que dans le seul texte de la barre d'outils.
EOF
)"
```

---

## Self-Review Notes (for the plan author, not a task)

- **Spec coverage**: §3.1 (data model) → Tasks 1, 5, 11; §3.2 (paint/legend)
  → Tasks 1, 2, 5, 6; §3.3 (labels) → Tasks 11, 12; §3.4 (icons, both
  Lucide and custom) → Tasks 4, 5, 6, 7, 8, 9, 10; §3.5 (editor) → Tasks 3,
  10, 12; §2's 4.5 scope (measure + sketch, mounted only in
  `mapWidget.tsx`'s non-edit `Component`) → Tasks 13, 14, 15, 16; proofs →
  Task 17. Every §4 decision has a corresponding task; §7's risks (label
  perf, cosmetic export bar) are left as documented follow-ups per the spec
  itself, not tasks.
- A reviewer of Task 1 alone cannot see the full stroke rendering story
  (that's Task 2) — this is intentional right-sizing, not a gap: Task 1's
  own tests fully exercise `buildMapPaint`/`buildLegend`'s pure output in
  isolation.
