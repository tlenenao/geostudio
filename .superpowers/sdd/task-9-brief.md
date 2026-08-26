## Task 9: Shell — `MapView` reads `layer.symbology` at render

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `symbologyToPaintInputs`, `buildMapPaint` from
  `../builder/widgets/mapSymbology`.

- [ ] **Step 1: Read the current `applyLayers` vector/feature branches**

Run: `grep -n "kind === \"vector\"\|kind === \"feature\"" shell/src/map/MapView.tsx`

Read the exact surrounding code (paint assembly per sub-layer, lines ~222-296
per earlier exploration) before editing — the plan shows the transformation
to apply, not a verbatim replacement of code you have not just re-read.

- [ ] **Step 2: Write the failing test**

Add to `shell/src/map/MapView.test.tsx` (find the existing test that
asserts on a rendered `fill-color`/paint for a vector or feature layer, to
reuse its MapLibre-mocking setup):

```tsx
test("a layer with symbology renders paint compiled from its frozen domain, ignoring any stale raw paint", () => {
  const layer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "feature",
    url: "u",
    paint: { "fill-color": "#000000" }, // stale/irrelevant once symbology is present
    symbology: {
      color: {
        field: "pop",
        mode: "numeric",
        palette: "sequential-blue",
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: "2026-08-23T00:00:00Z",
      },
    },
  };
  // (render MapView with this single layer, following whichever existing
  // test in this file already asserts on setPaintProperty/addLayer calls —
  // copy its exact mock/assertion mechanics)
});
```

Fill in the actual render/assertion mechanics by copying the nearest
existing paint-assertion test in this file verbatim, then swap in the
`symbology`-bearing layer above and assert the resulting paint uses the
`interpolate` shape from `#dbeafe`→`#1e3a8a` (the `sequential-blue`
palette), not `"#000000"`.

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t symbology`
Expected: FAIL — `paint` still comes from the raw `layer.paint`.

- [ ] **Step 4: Implement**

In `shell/src/map/MapView.tsx`'s `applyLayers`, wherever `layer.paint ??
{}` (or equivalent) is read for `kind === "vector"` and `kind ===
"feature"`, replace with a small helper computed once per layer:

```ts
function effectivePaint(layer: Extract<MapLayer, { kind: "vector" | "feature" }>): Record<string, unknown> {
  if (!layer.symbology) return layer.paint ?? {};
  const geometryKind =
    layer.kind === "vector" ? (layer.geometryKind ?? "polygon") : "polygon"; // feature layers: renderAs already carries geometry choice, see below
  const { encodings, colorDomain, sizeDomain, palette } = symbologyToPaintInputs(layer.symbology, undefined);
  return buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette).paint;
}
```

For `kind === "feature"`, the existing code already derives `renderAs` from
`layer.renderAs` (author-set), not from a detected `geometryKind` — pass the
render-as-implied geometry kind consistently with whatever `applyLayers`
already does today for that layer kind (read the exact existing branch
before writing this, per Step 1 — do not invent a new geometryKind
inference here).

For the `vector` kind's existing per-sub-layer split (point/line/polygon
sub-layers by `geometryKind`, from SP-24's I1 fix), call `effectivePaint`
once for the whole layer and keep applying the existing `paintFor(...,
paintPrefix)` filter on its result exactly as today — `buildMapPaint`'s
output already only contains the single `renderAs`-appropriate paint key
(e.g. `"fill-color"`), so this composes without change to the sub-layer
splitting logic itself.

- [ ] **Step 5: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, all tests (no regression on layers without `symbology`,
which must still read `layer.paint` exactly as before).

- [ ] **Step 6: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): MapView compile le paint depuis symbology quand elle est présente

Aucun appel réseau : le domaine est déjà figé dans la config.
layer.paint reste le chemin manuel pour toute couche sans symbology.
EOF
)"
```

---

