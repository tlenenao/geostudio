## Task 2: `MapLayer.renderAs` — additive field honored by `MapView`

**Files:**
- Modify: `shell/src/api/types.ts:62`
- Modify: `shell/src/map/MapView.tsx:56-58`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: nothing from Task 1 (independent, purely additive change to shared map rendering).
- Produces (consumed by Task 3): `MapLayer` (kind `"feature"`) now accepts an optional `renderAs?: "fill" | "circle" | "line"`; `MapView` renders that MapLibre layer `type` instead of the hard-coded `"fill"`, defaulting to `"fill"` when absent.

- [ ] **Step 1: Write the failing tests**

In `shell/src/map/MapView.test.tsx`, add these three tests right after the existing `"re-applies layers when config.layers changes"` test (after its closing `});`, before `"reports view changes on moveend"`):

```ts
test("renders a circle layer for a feature layer with renderAs \"circle\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "pts", title: "Points", visible: true, kind: "feature", url: "https://fs/pts", renderAs: "circle", paint: { "circle-color": "#111" } }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("pts")).toMatchObject({ type: "circle", source: "pts", paint: { "circle-color": "#111" } });
});

test("renders a line layer for a feature layer with renderAs \"line\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "lns", title: "Lignes", visible: true, kind: "feature", url: "https://fs/lns", renderAs: "line" }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("lns")).toMatchObject({ type: "line", source: "lns" });
});

test("defaults a feature layer to fill when renderAs is not set", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "poly", title: "Polygones", visible: true, kind: "feature", url: "https://fs/poly" }],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("poly")).toMatchObject({ type: "fill", source: "poly" });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npm run test -- MapView.test.tsx`
Expected: FAIL — the first two new tests fail (`type` is `"fill"` for both, since MapView doesn't know about `renderAs` yet, and TypeScript itself would already reject `renderAs` as an unknown property on `MapLayer` until Step 3's type change lands). The third test passes already (it doesn't exercise anything new).

- [ ] **Step 3: Add `renderAs` to `MapLayer` and honor it in `MapView`**

In `shell/src/api/types.ts`, change line 62 from:

```ts
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown> }
```

to:

```ts
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
```

In `shell/src/map/MapView.tsx`, change (lines 56-58):

```ts
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
```

to:

```ts
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: layer.renderAs ?? "fill", source: layer.id, paint: layer.paint ?? {} });
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npm run test -- MapView.test.tsx`
Expected: PASS — all tests green, including the 3 new ones.

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS — no other suite references `MapLayer`'s `feature` variant in a way that would break from an additive optional field.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/api/types.ts src/map/MapView.tsx src/map/MapView.test.tsx
git commit -m "feat(shell): MapLayer gains an optional renderAs, honored by MapView for feature layers (SP-14h)"
```

---

