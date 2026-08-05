## Task 5: Shell — `bboxFromGeometry` util + `derivePatch` resolution

**Files:**
- Create: `shell/src/lib/geometryBbox.ts`
- Test: `shell/src/lib/geometryBbox.test.ts` (new)
- Modify: `shell/src/lib/analyticsPatch.ts` (full rewrite of `derivePatch`, factor out `applyCrossFilterValue`)
- Test: `shell/src/lib/analyticsPatch.test.ts` (append)

**Interfaces:**
- Consumes: `CrossFilterLink`, `DatasetConfig` (Task 4), `CrossFilterEntry.geometry` (Task 4).
- Produces: `bboxFromGeometry(geometry: unknown): [number, number, number, number] | null` (pure, no dependency on turf — none exists in this repo). `derivePatch` now also resolves inter-dataset links: attribute links translate to `targetField`/`targetField__in`/`targetField__gte`+`targetField__lte`; spatial/bbox links add `patch.bbox`; spatial/exact links add `patch.geomIntersects` (raw geometry object, consumed by Task 6's `buildAggregateBody` change).

- [ ] **Step 1: Write the failing `bboxFromGeometry` tests**

Create `shell/src/lib/geometryBbox.test.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { bboxFromGeometry } from "./geometryBbox";

test("returns a degenerate bbox for a Point", () => {
  expect(bboxFromGeometry({ type: "Point", coordinates: [2.4, 46.6] })).toEqual([2.4, 46.6, 2.4, 46.6]);
});

test("returns the enclosing bbox for a Polygon", () => {
  const polygon = {
    type: "Polygon",
    coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]],
  };
  expect(bboxFromGeometry(polygon)).toEqual([2.0, 48.0, 3.0, 49.0]);
});

test("returns the enclosing bbox across a MultiPolygon's parts", () => {
  const multi = {
    type: "MultiPolygon",
    coordinates: [
      [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
      [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
    ],
  };
  expect(bboxFromGeometry(multi)).toEqual([0, 0, 11, 11]);
});

test("returns null for undefined, null, or a non-geometry value", () => {
  expect(bboxFromGeometry(undefined)).toBeNull();
  expect(bboxFromGeometry(null)).toBeNull();
  expect(bboxFromGeometry({ foo: "bar" })).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement `geometryBbox.ts`**

Create `shell/src/lib/geometryBbox.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
// Recursively walks GeoJSON coordinate arrays (any depth: Point, LineString,
// Polygon, Multi*) to compute an enclosing [minX, minY, maxX, maxY] — no
// turf/geojson dependency, neither is present in this repo (DataRecord.geometry
// is typed `unknown` for the same reason, api/types.ts:351).
function walk(coords: unknown, acc: [number, number, number, number]): void {
  if (Array.isArray(coords) && typeof coords[0] === "number") {
    const [x, y] = coords as [number, number];
    if (x < acc[0]) acc[0] = x;
    if (y < acc[1]) acc[1] = y;
    if (x > acc[2]) acc[2] = x;
    if (y > acc[3]) acc[3] = y;
    return;
  }
  if (Array.isArray(coords)) coords.forEach((c) => walk(c, acc));
}

export function bboxFromGeometry(geometry: unknown): [number, number, number, number] | null {
  if (!geometry || typeof geometry !== "object" || !("coordinates" in geometry)) return null;
  const coords = (geometry as { coordinates: unknown }).coordinates;
  const acc: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  walk(coords, acc);
  if (!isFinite(acc[0])) return null;
  return acc;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the failing `derivePatch` tests**

Append to `shell/src/lib/analyticsPatch.test.ts`:

```typescript
const linked: DatasetConfig = {
  source: "collection", collectionId: "communes", columns: {},
  crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "attribute", sourceField: "commune", targetField: "nom_commune" }],
};

test("translates an attribute link from another dataset's active cross-filter", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({ nom_commune: "Brive" });
});

test("ignores an attribute link when the active field doesn't match sourceField", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "autre_champ", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({});
});

test("ignores a link that doesn't target this source's dataset", () => {
  const elsewhere = { ...linked, crossFilterLinks: [{ targetDatasetId: "ds-999", mode: "attribute" as const, sourceField: "commune", targetField: "nom_commune" }] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": elsewhere })).toEqual({});
});

test("translates a spatial/bbox link into a bbox patch derived from the entry's geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    bbox: "2,48,3,49",
  });
});

test("translates a spatial/exact link into a geomIntersects patch carrying the raw geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "exact" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    geomIntersects: polygon,
  });
});

test("ignores a spatial link when the active entry has no geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({});
});

test("does not resolve a link declared on the same dataset as the target source (no self-link)", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-1" } },
  };
  // dataset "ds-1" has no crossFilterLinks of its own here — this just proves the
  // direct same-dataset path (already tested above) and the link path don't double-fire.
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});
```

Add `DatasetConfig` to the file's type import from `../api/types` if not already present (it already is, per the file's existing `import type { DataSource, DatasetConfig } from "../api/types";`).

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: FAIL — `derivePatch` doesn't yet look at any dataset's `crossFilterLinks`, so every new "translates"/"ignores a link..." test that expects a non-empty patch gets `{}` instead.

- [ ] **Step 7: Implement `derivePatch`**

Replace the full contents of `shell/src/lib/analyticsPatch.ts`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState, CrossFilterValue } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { bboxFromGeometry } from "./geometryBbox";

// Pure translation of the global analytics context into query-filter keys
// for one DataSource, mirroring the __gte/__lte/__in suffixes the core
// understands (features/repository.py, analytics/aggregate.py). `datasets`
// keys are DatasetConfig objects already resolved by the caller (DataContext)
// — this function never fetches.
export function derivePatch(
  source: DataSource,
  ctx: AnalyticsContextState,
  datasets: Record<string, DatasetConfig>,
): Record<string, unknown> {
  if (!source.datasetId) return {};
  const dataset = datasets[source.datasetId];
  if (!dataset) return {};

  const patch: Record<string, unknown> = {};

  if (ctx.timeRange && dataset.timeField) {
    patch[`${dataset.timeField}__gte`] = ctx.timeRange.from;
    patch[`${dataset.timeField}__lte`] = ctx.timeRange.to;
  }

  if (ctx.extent && dataset.reactsToExtent) {
    patch.bbox = ctx.extent.join(",");
  }

  const directCrossFilter = ctx.crossFilter[source.datasetId];
  if (directCrossFilter && directCrossFilter.originSourceId !== source.id) {
    applyCrossFilterValue(patch, directCrossFilter.field, directCrossFilter.value);
  }

  // SP-14n — cross-filter inter-datasets : pour chaque AUTRE dataset avec un
  // cross-filter actif, vérifier s'il déclare un lien vers le dataset de
  // cette source, et traduire en conséquence. Un seul saut (pas de chaînage
  // transitif) ; en cas de liens contradictoires vers la même cible, le
  // dernier résolu gagne (limite documentée, spec §1).
  for (const [originDatasetId, entry] of Object.entries(ctx.crossFilter)) {
    if (!entry || originDatasetId === source.datasetId) continue;
    const originDataset = datasets[originDatasetId];
    const link = originDataset?.crossFilterLinks?.find((l) => l.targetDatasetId === source.datasetId);
    if (!link) continue;
    if (link.mode === "attribute") {
      if (entry.field === link.sourceField) applyCrossFilterValue(patch, link.targetField, entry.value);
    } else if (entry.geometry !== undefined) {
      if (link.precision === "bbox") {
        const bbox = bboxFromGeometry(entry.geometry);
        if (bbox) patch.bbox = bbox.join(",");
      } else {
        patch.geomIntersects = entry.geometry;
      }
    }
  }

  return patch;
}

function applyCrossFilterValue(patch: Record<string, unknown>, field: string, value: CrossFilterValue): void {
  if (Array.isArray(value)) {
    patch[`${field}__in`] = value.join(",");
  } else if (typeof value === "object") {
    patch[`${field}__gte`] = value.from;
    patch[`${field}__lte`] = value.to;
  } else {
    patch[field] = value;
  }
}
```

Add `CrossFilterValue` to the existing import from `../builder/AnalyticsContext` in `analyticsPatch.test.ts` if a test references it directly (it doesn't need to — the tests above only construct plain object literals typed as `AnalyticsContextState`, already imported).

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: PASS (all tests, including the 7 new ones — the pre-existing same-dataset tests must still pass unchanged, since `applyCrossFilterValue` is a byte-for-byte extraction of the same three branches, not a behavior change).

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/lib/geometryBbox.ts shell/src/lib/geometryBbox.test.ts shell/src/lib/analyticsPatch.ts shell/src/lib/analyticsPatch.test.ts
git commit -m "feat(shell): resolve cross-filter links (attribute + spatial) in derivePatch (SP-14n)"
```

---

