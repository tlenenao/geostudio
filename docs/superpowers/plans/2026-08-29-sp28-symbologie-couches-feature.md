# Symbologie des couches `feature` (URL GeoJSON) — SP-28 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author add a map layer by pasting a raw GeoJSON URL in the map editor's `LayerPicker`, and style it with the full `LayerSymbology` editor (categorical/numeric/classed color, including Jenks) — today `LayerSymbologyEditor` returns `null` for these layers and there is no way to add one at all.

**Architecture:** A new pure module, `shell/src/map/geojsonIntrospect.ts`, fetches a GeoJSON URL once (client-side, in the browser — never through the core) and implements the exact `StatQueryFn`/`SampleFieldFn` contracts `MapSymbologyEditor` already consumes, computed in memory over the parsed features instead of a server aggregate. `LayersPanel.tsx` wires this in for `kind: "feature"` layers (same component, same `MapSymbologyEditor`, only the three functions its two editors pass down change). `LayerPicker.tsx` gets a new "add by URL" form, mirroring the existing "tileset 3D by URL" one, that also detects the layer's `renderAs` and primes the fetch cache so the panel doesn't refetch.

**Tech Stack:** React, TypeScript, `@tanstack/react-query` (`useQuery`/`useQueryClient`), Vitest + Testing Library, Playwright.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-29-sp28-symbologie-couches-feature-design.md`.
- No core/schema/migration changes — `symbology`/`popup` on `kind: "feature"` already round-trip untyped through `core/app/configs/schemas.py`.
- No OpenAPI/TS regeneration needed — verify this explicitly at the end (CLAUDE.md trap #1), don't skip the check just because nothing obviously changed.
- The introspection fetch is a plain `fetch()`, never routed through `ItemClient` — it talks to an arbitrary third-party URL, not the core catalog (CLAUDE.md rule 1 is about catalog access, not this).
- Global test setup (`shell/src/test/setup.ts`) runs MSW with `onUnhandledRequest: "error"` for every test file. Any test that renders a `kind: "feature"` layer through `LayersPanel` now triggers a real `fetch()` on mount (via the new `useQuery`) — it MUST be pre-stubbed with `vi.stubGlobal("fetch", ...)`, cleaned up with `vi.unstubAllGlobals()` in `afterEach`, or MSW throws. This is the established pattern already used in `shell/src/map/MapMeasureSketchToolbar.test.tsx`.
- `MapView.tsx` and its tests (`MapView.test.tsx`) are NOT touched by this plan — it never fetches/parses GeoJSON itself (MapLibre does that internally as a native GeoJSON source), and `symbology` resolution happens only at author time in the editor. Nothing in this plan changes that.
- `shell/src/builder/widgets/mapWidget.tsx` (the app/dashboard map widget) is explicitly out of scope — different resolution path (a `DataSource`/`datasetId`, not a raw URL), already shipped in SP-27, left untouched.

---

## Task 1: `geojsonIntrospect.ts` — client-side GeoJSON introspection

**Files:**
- Create: `shell/src/map/geojsonIntrospect.ts`
- Test: `shell/src/map/geojsonIntrospect.test.ts`

**Interfaces:**
- Consumes: `DataRecord` (`shell/src/api/types.ts:609`, `{ id: string | number; properties: Record<string, unknown>; geometry?: unknown }`), `StatQueryFn`/`SampleFieldFn` (`shell/src/builder/widgets/mapSymbology.ts:366-367`, `StatQueryFn = (query: Record<string, unknown>) => Promise<DataRecord[]>`, `SampleFieldFn = (field: string, limit: number) => Promise<number[]>`).
- Produces (consumed by Task 2 and Task 3): `fetchFeatureCollection(url: string): Promise<GeoJSON.FeatureCollection>`, `listFields(fc: GeoJSON.FeatureCollection): string[]`, `makeStatQueryFn(fc: GeoJSON.FeatureCollection): StatQueryFn`, `makeSampleFieldFn(fc: GeoJSON.FeatureCollection): SampleFieldFn`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/geojsonIntrospect.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, test, vi } from "vitest";
import {
  fetchFeatureCollection,
  listFields,
  makeSampleFieldFn,
  makeStatQueryFn,
} from "./geojsonIntrospect";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fcWithValues(field: string, values: unknown[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: values.map((v) => ({
      type: "Feature",
      properties: { [field]: v },
      geometry: null,
    })),
  };
}

describe("fetchFeatureCollection", () => {
  test("resolves a valid FeatureCollection", async () => {
    const fc = { type: "FeatureCollection", features: [] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).resolves.toEqual(fc);
  });

  test("rejects on a non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }),
    );
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).rejects.toThrow(/404/);
  });

  test("rejects when the body is not a GeoJSON FeatureCollection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ type: "Feature" }) }),
    );
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).rejects.toThrow(
      /FeatureCollection/,
    );
  });
});

describe("listFields", () => {
  test("unions properties across heterogeneous features, sorted", () => {
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: { nom: "A", pop: 10 }, geometry: null },
        { type: "Feature", properties: { region: "X" }, geometry: null },
      ],
    };
    expect(listFields(fc)).toEqual(["nom", "pop", "region"]);
  });

  test("returns an empty list for an empty collection", () => {
    expect(listFields({ type: "FeatureCollection", features: [] })).toEqual([]);
  });
});

describe("makeStatQueryFn", () => {
  test("groupBy returns distinct values in first-appearance order", async () => {
    const fc = fcWithValues("categorie", ["a", "b", "a", "c"]);
    const rows = await makeStatQueryFn(fc)({ groupBy: "categorie" });
    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
  });

  test("measures min and max over numeric values, ignoring non-numeric ones", async () => {
    const fc = fcWithValues("pop", [30, "n/a", 10, null, 20]);
    const rows = await makeStatQueryFn(fc)({
      measures: [
        { field: "pop", agg: "min", label: "min" },
        { field: "pop", agg: "max", label: "max" },
      ],
    });
    expect(rows).toEqual([{ id: "", properties: { min: 10, max: 30 } }]);
  });

  test("measures percentile interpolates linearly over sorted values", async () => {
    const fc = fcWithValues("pop", [10, 20, 30, 40]);
    const rows = await makeStatQueryFn(fc)({
      measures: [{ field: "pop", agg: "percentile", label: "q50", p: 50 }],
    });
    expect(rows).toEqual([{ id: "", properties: { q50: 25 } }]);
  });

  test("degenerates to 0 rather than NaN on an empty collection", async () => {
    const fc = fcWithValues("pop", []);
    const rows = await makeStatQueryFn(fc)({
      measures: [
        { field: "pop", agg: "min", label: "min" },
        { field: "pop", agg: "max", label: "max" },
      ],
    });
    expect(rows).toEqual([{ id: "", properties: { min: 0, max: 0 } }]);
  });
});

describe("makeSampleFieldFn", () => {
  test("returns finite numeric values only, capped at the limit", async () => {
    const fc = fcWithValues("pop", [10, "n/a", 20, null, 30, 40]);
    await expect(makeSampleFieldFn(fc)("pop", 2)).resolves.toEqual([10, 20]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/geojsonIntrospect.test.ts`
Expected: FAIL — `Cannot find module './geojsonIntrospect'` (the file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `shell/src/map/geojsonIntrospect.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { DataRecord } from "../api/types";
import type { SampleFieldFn, StatQueryFn } from "../builder/widgets/mapSymbology";

export async function fetchFeatureCollection(url: string): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Impossible de charger ${url} (HTTP ${res.status})`);
  const data: unknown = await res.json();
  if (
    typeof data !== "object" ||
    data === null ||
    (data as { type?: unknown }).type !== "FeatureCollection" ||
    !Array.isArray((data as { features?: unknown }).features)
  ) {
    throw new Error(`${url} n'est pas une FeatureCollection GeoJSON valide`);
  }
  return data as GeoJSON.FeatureCollection;
}

export function listFields(fc: GeoJSON.FeatureCollection): string[] {
  const fields = new Set<string>();
  for (const feature of fc.features) {
    for (const key of Object.keys(feature.properties ?? {})) fields.add(key);
  }
  return [...fields].sort();
}

function numericValues(fc: GeoJSON.FeatureCollection, field: string): number[] {
  const values: number[] = [];
  for (const feature of fc.features) {
    const raw = (feature.properties ?? {})[field];
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isFinite(n)) values.push(n);
  }
  return values;
}

// Interpolation linéaire standard (méthode "R-7"/numpy par défaut) : pas
// besoin d'être identique bit à bit à l'agrégat SQL du cœur (spec §3.1) —
// juste d'un percentile usuel, pour rester visuellement cohérent d'une
// couche `vector` à une couche `feature`.
function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (idx - lower);
}

type Measure = { field: string; agg: string; label: string; p?: number };

// N'implémente que les trois agrégats que computeColorDomain/computeSizeDomain
// (mapSymbology.ts) émettent réellement : min, max, percentile. Les autres
// agrégats du catalogue SP-23 (avg, sum, countDistinct, median, stddev...) ne
// sont jamais demandés par ce chemin — les ajouter serait mort dès l'écriture.
export function makeStatQueryFn(fc: GeoJSON.FeatureCollection): StatQueryFn {
  return async (query) => {
    const groupBy = (query as { groupBy?: string }).groupBy;
    if (typeof groupBy === "string") {
      const seen = new Map<string, DataRecord>();
      for (const feature of fc.features) {
        const raw = (feature.properties ?? {})[groupBy];
        if (raw === undefined || raw === null) continue;
        const id = String(raw);
        if (!seen.has(id)) seen.set(id, { id, properties: {} });
      }
      return [...seen.values()];
    }
    const measures = (query as { measures?: Measure[] }).measures ?? [];
    const properties: Record<string, number> = {};
    for (const measure of measures) {
      const sorted = numericValues(fc, measure.field).sort((a, b) => a - b);
      if (measure.agg === "min") properties[measure.label] = sorted[0] ?? 0;
      else if (measure.agg === "max") properties[measure.label] = sorted[sorted.length - 1] ?? 0;
      else if (measure.agg === "percentile") {
        properties[measure.label] = percentile(sorted, measure.p ?? 0);
      }
    }
    return [{ id: "", properties }];
  };
}

export function makeSampleFieldFn(fc: GeoJSON.FeatureCollection): SampleFieldFn {
  return async (field, limit) => numericValues(fc, field).slice(0, limit);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/geojsonIntrospect.test.ts`
Expected: PASS — 10 tests.

- [ ] **Step 5: Type-check and lint this file in isolation**

Run: `cd shell && npx tsc --noEmit && npx eslint src/map/geojsonIntrospect.ts src/map/geojsonIntrospect.test.ts`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/map/geojsonIntrospect.ts shell/src/map/geojsonIntrospect.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): introspection GeoJSON côté client pour les couches feature

Fetch + parse d'une URL GeoJSON en mémoire, avec des implémentations de
StatQueryFn/SampleFieldFn (mapSymbology.ts) calculées sur les entités
déjà chargées — pas de nouvel appel au cœur. Prépare le câblage de
LayerSymbologyEditor pour les couches sans collectionId (SP-28).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Wire `LayersPanel.tsx` — symbology and popup for `kind: "feature"` layers

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify (fix tests broken by the new eager fetch): `shell/src/map/LayersPanel.test.tsx`
- Modify (same reason — it renders the real `LayersPanel` with a `kind: "feature"` layer): `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `fetchFeatureCollection`, `listFields`, `makeStatQueryFn`, `makeSampleFieldFn` from `./geojsonIntrospect`.
- Produces: no new exports — `LayerSymbologyEditor`/`LayerPopupEditor` remain internal to `LayersPanel.tsx`. The react-query cache key `["feature-geojson", url]` becomes a shared contract with Task 3 (LayerPicker primes it).

- [ ] **Step 1: Write the failing tests**

In `shell/src/map/LayersPanel.test.tsx`, first fix the imports and add the global fetch stub every test in this file now needs (every fixture layer here is `kind: "feature"`, so `LayerSymbologyEditor`/`LayerPopupEditor` will eagerly `fetch()` their `url` on mount — MSW's `onUnhandledRequest: "error"` throws on any unstubbed call):

Change the import line:

```ts
import { afterEach, beforeEach, expect, test, vi } from "vitest";
```

Add right after the `layers` constant (before `function renderPanel`):

```ts
// Chaque couche "feature" ci-dessus déclenche désormais un fetch de son
// `url` au montage (Task 2, SP-28) — sans repli, MSW (onUnhandledRequest:
// "error", src/test/setup.ts) ferait échouer tout test de ce fichier qui
// n'attend rien de particulier de cette requête. Un rejet par défaut
// reproduit exactement le comportement d'avant (availableFields=[]) pour
// les tests qui ne testent pas la symbologie feature elle-même.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});
afterEach(() => {
  vi.unstubAllGlobals();
});
```

Then add these tests at the end of the file (after the last `test(...)` block):

```ts
test("a feature layer without a collection lists fields from its fetched GeoJSON in the popup editor", async () => {
  const onChange = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: { nom: "A" }, geometry: null }],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  renderPanel([featureLayer], onChange);
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(await screen.findByRole("checkbox", { name: "nom" })).toBeInTheDocument();
});

test("a feature layer without a collection computes Jenks classes from its own GeoJSON", async () => {
  const onChange = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((pop, i) => ({
      type: "Feature",
      properties: { pop },
      geometry: { type: "Point", coordinates: [i, i] },
    })),
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
  vi.stubGlobal("fetch", fetchMock);
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider
        client={{ listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient}
      >
        <SymbologyHost initialLayers={[featureLayer]} onLayersChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith("https://ex.test/points.geojson"),
  );
  await userEvent.type(screen.getByLabelText("Champ couleur"), "pop");
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  await userEvent.selectOptions(screen.getByLabelText("Méthode de classification"), "jenks");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      symbology: expect.objectContaining({
        color: expect.objectContaining({
          domain: expect.objectContaining({ kind: "numeric-classed" }),
        }),
      }),
    }),
  ]);
});

test("a feature layer whose GeoJSON fails to load still shows a symbology editor with no crash", async () => {
  const onChange = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  renderPanel([featureLayer], onChange);
  expect(await screen.findByLabelText("Champ couleur")).toHaveValue("");
});
```

Add `waitFor` to the existing `@testing-library/react` import line at the top of the file:

```ts
import { render, screen, waitFor } from "@testing-library/react";
```

- [ ] **Step 2: Run tests to verify the new ones fail (and the old ones still pass once the stub is added)**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
Expected: the 3 new tests FAIL (`LayerSymbologyEditor`/`LayerPopupEditor` still return `[]`/`null` for feature layers — the popup checkbox for "nom" and the "Champ couleur" input plus categorical/Jenks behavior aren't there yet). All pre-existing tests in the file PASS (the `beforeEach` fetch stub neutralizes the newly-added mount-time fetch without changing their assertions).

- [ ] **Step 3: Write the implementation**

In `shell/src/map/LayersPanel.tsx`, add the import:

```ts
import { fetchFeatureCollection, listFields, makeSampleFieldFn, makeStatQueryFn } from "./geojsonIntrospect";
```

Replace the two functions `LayerPopupEditor` and `LayerSymbologyEditor` (currently lines 9-90) with:

```tsx
// Une couche "feature" n'a pas de collection interrogeable : son schéma vient
// du GeoJSON qu'elle pointe elle-même. Une seule requête partagée par les
// deux éditeurs ci-dessous (react-query dédoublonne par clé — un seul fetch
// réseau même si popup et symbologie sont montés en même temps, ce qui est
// le cas ici).
function useFeatureLayerGeoJson(layer: Extract<MapLayer, { kind: "vector" | "feature" }>) {
  const url = layer.kind === "feature" ? layer.url : undefined;
  return useQuery({
    queryKey: ["feature-geojson", url],
    queryFn: () => fetchFeatureCollection(url!),
    enabled: Boolean(url),
  });
}

// Charge le schéma de la collection sous-jacente pour offrir la liste des
// champs à l'auteur — patron déjà établi par CrossFilterLinkEditor.tsx:28-34
// (useQuery inline, pas de hook dédié dans api/hooks.ts pour ce besoin).
function LayerPopupEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  const featureGeojson = useFeatureLayerGeoJson(layer);
  return (
    <PopupEditor
      value={layer.popup}
      // Sans collectionId : couche "feature" (URL GeoJSON), les champs
      // viennent de l'introspection côté client (geojsonIntrospect.ts,
      // Task 2 SP-28) une fois son fetch résolu ; avant ça, liste vide comme
      // pour une collection dont le schéma charge encore.
      availableFields={
        collectionId
          ? (schema.data?.fields.map((f) => f.name) ?? [])
          : (featureGeojson.data ? listFields(featureGeojson.data) : [])
      }
      onChange={(popup) => onChangeLayer({ ...layer, popup })}
    />
  );
}

// Même patron que LayerPopupEditor ci-dessus. Sans collectionId (couche
// "feature", URL GeoJSON) : les trois fonctions que MapSymbologyEditor
// attend (availableFields/runStatistics/sampleField) sont dérivées du
// GeoJSON introspecté côté client (Task 2, SP-28) au lieu d'une requête au
// cœur — jenksAvailable reste à son défaut `true` : contrairement à la
// couche "feature" du widget carte (mapWidget.tsx, adossée à un DataSource
// distant sans valeurs brutes disponibles), ici les valeurs sont locales et
// Jenks fonctionne réellement.
function LayerSymbologyEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  const featureGeojson = useFeatureLayerGeoJson(layer);
  const fc = featureGeojson.data;
  const notReady = async (): Promise<never> => {
    throw new Error("La couche GeoJSON n'est pas encore chargée");
  };
  return (
    <MapSymbologyEditor
      value={layer.symbology}
      availableFields={
        collectionId ? (schema.data?.fields.map((f) => f.name) ?? []) : (fc ? listFields(fc) : [])
      }
      themeColors={undefined} // no Theme on a standalone MapConfig (spec §1)
      runStatistics={
        collectionId
          ? (query) =>
              client.queryDataSource({
                id: `map-symbology-${collectionId}`,
                type: "statistics",
                service: "core",
                layer: collectionId,
                query,
              })
          : fc
            ? makeStatQueryFn(fc)
            : notReady
      }
      sampleField={
        collectionId
          ? (field, limit) => client.sampleCollectionField(collectionId, field, limit)
          : fc
            ? makeSampleFieldFn(fc)
            : notReady
      }
      // `?.()` OBLIGATOIRE, pas cosmétique (défaut n° 5 de la brief Task 12) :
      // ce hôte est rendu dans des tests existants avec des ItemClient
      // PARTIELS (LayersPanel.test.tsx:48 et :103). Sans `?.`,
      // `client.listMapIcons()` lève SYNCHRONIQUEMENT dans le callback
      // d'effet et fait échouer le rendu de ces tests, verts aujourd'hui —
      // le `.catch()` de l'effet n'attrape rien, il n'y a pas encore de
      // promesse.
      listCustomIcons={() => client.listMapIcons?.() ?? Promise.resolve([])}
      uploadCustomIcon={(file, title, category) =>
        // UN SEUL appel (D7) : plus de presign → PUT → POST. Le cœur reçoit
        // les octets, choisit la clé S3, assainit, puis écrit.
        client.uploadMapIcon(file, title, category)
      }
      deleteCustomIcon={(id) => client.deleteMapIcon(id)}
      onChange={(symbology) => onChangeLayer({ ...layer, symbology })}
    />
  );
}
```

Remove the old `if (!collectionId) return null;` line entirely — it no longer exists in the replacement above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS — all tests, old and new.

- [ ] **Step 5: Fix `MapEditorPage.test.tsx`, which also mounts a real `LayersPanel` with a `kind: "feature"` layer**

In `shell/src/pages/MapEditorPage.test.tsx`, update the existing `beforeEach`/`afterEach`:

```ts
beforeEach(() => {
  mapInstances.length = 0;
  overlayInstances.length = 0;
  // La couche "feature" de `config` (ci-dessous) déclenche désormais un
  // fetch de son `url` au montage de LayersPanel (Task 2, SP-28) — MSW
  // (onUnhandledRequest: "error") ferait échouer ces tests sans ce repli.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});

afterEach(() => {
  delete document.body.dataset.exportReady;
  vi.unstubAllGlobals();
});
```

- [ ] **Step 6: Run the full shell test suite to confirm no other test broke**

Run: `cd shell && npm run test`
Expected: PASS, same file/test counts as the CLAUDE.md baseline plus the 3 new tests in `LayersPanel.test.tsx` (no new failures anywhere else — in particular check there is no other test file rendering `LayersPanel` or `MapEditorPage` with a `kind: "feature"` layer that this step missed; if `npm run test` surfaces one, apply the same `vi.stubGlobal("fetch", ...)` / `vi.unstubAllGlobals()` fix there too before proceeding).

- [ ] **Step 7: Type-check and lint**

Run: `cd shell && npm run build && npm run lint`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): symbologie et popup pour les couches feature dans LayersPanel

LayerSymbologyEditor ne retourne plus null pour une couche kind:"feature"
sans collectionId : champs, domaines et Jenks viennent désormais de
l'introspection GeoJSON côté client (geojsonIntrospect.ts, Task 1),
même pattern de dégradation que LayerPopupEditor. jenksAvailable reste
vrai ici — les valeurs sont locales, contrairement au widget carte.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `LayerPicker.tsx` — add a layer by GeoJSON URL

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx`
- Modify: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `fetchFeatureCollection` from `./geojsonIntrospect`; `detectGeometryKind`, `renderAsFor` from `../builder/widgets/mapSymbology` (`shell/src/builder/widgets/mapSymbology.ts:193-204`).
- Produces: primes the react-query cache under `["feature-geojson", url]` — the exact key `useFeatureLayerGeoJson` (Task 2) reads, via `useQueryClient().setQueryData`.

- [ ] **Step 1: Write the failing tests**

In `shell/src/map/LayerPicker.test.tsx`, add `afterEach`, `waitFor`, and `useQueryClient`-adjacent imports:

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
```

Add at module scope, right after the imports:

```ts
afterEach(() => {
  vi.unstubAllGlobals();
});
```

Add these tests at the end of the file:

```ts
test("adds a feature layer from the manual GeoJSON URL form, with renderAs detected from its geometry", async () => {
  const onAdd = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
    ],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Points d'intérêt");
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/poi.geojson",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Points d'intérêt",
    visible: true,
    url: "https://external.test/poi.geojson",
    renderAs: "circle",
  });
});

test("adds the layer even when the GeoJSON probe fails, without a renderAs, and shows an inline warning", async () => {
  const onAdd = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("CORS")));
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Zones");
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/zones.geojson",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Zones",
    url: "https://external.test/zones.geojson",
  });
  expect(layer).not.toHaveProperty("renderAs");
  expect(screen.getByRole("alert")).toHaveTextContent(/n'a pas pu être vérifié/);
});

test("disables the GeoJSON URL add button until both title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter la couche" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Zones");
  expect(button).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/zones.geojson",
  );
  expect(button).toBeEnabled();
});

test("clears the GeoJSON URL form after adding and primes the introspection cache for that URL", async () => {
  const onAdd = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
    ],
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
  vi.stubGlobal("fetch", fetchMock);
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const titleInput = screen.getByLabelText("Titre de la couche GeoJSON") as HTMLInputElement;
  const urlInput = screen.getByLabelText("URL du GeoJSON") as HTMLInputElement;
  await userEvent.type(titleInput, "Points");
  await userEvent.type(urlInput, "https://external.test/points.geojson");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  expect(titleInput.value).toBe("");
  expect(urlInput.value).toBe("");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(qc.getQueryData(["feature-geojson", "https://external.test/points.geojson"])).toEqual(fc);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx`
Expected: the 4 new tests FAIL (`getByLabelText("Titre de la couche GeoJSON")` etc. don't exist yet). All pre-existing tests still PASS.

- [ ] **Step 3: Write the implementation**

In `shell/src/map/LayerPicker.tsx`, update imports:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { detectGeometryKind, renderAsFor } from "../builder/widgets/mapSymbology";
import { fetchFeatureCollection } from "./geojsonIntrospect";
import { Button } from "../ui/button";
```

Add state and the handler inside `LayerPicker`, right after the existing `tiles3dTitle`/`tiles3dUrl` state and before `addTiles3D`:

```tsx
  const [featureTitle, setFeatureTitle] = useState("");
  const [featureUrl, setFeatureUrl] = useState("");
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  const queryClient = useQueryClient();

  async function addFeatureLayer() {
    const title = featureTitle.trim();
    const url = featureUrl.trim();
    if (!title || !url) return;
    setFeatureBusy(true);
    setFeatureError(null);
    let renderAs: "fill" | "circle" | "line" | undefined;
    try {
      const fc = await fetchFeatureCollection(url);
      renderAs = renderAsFor(detectGeometryKind(fc.features[0]?.geometry));
      // Amorce le cache que LayersPanel.tsx lit sous la même clé
      // (useFeatureLayerGeoJson) : ouvrir tout de suite le panneau de
      // symbologie de cette couche ne refait pas ce fetch.
      queryClient.setQueryData(["feature-geojson", url], fc);
    } catch {
      // L'URL est ajoutée quand même : la même URL, si elle échoue ici
      // (CORS, en-têtes différents...), échouera de la même façon pour
      // MapLibre au rendu — ce n'est pas une régression, juste un défaut
      // qu'on ne peut pas prédire sans que MapView tente lui-même le rendu.
      setFeatureError(
        "Couche ajoutée, mais son contenu n'a pas pu être vérifié (l'URL sera quand même utilisée pour l'affichage).",
      );
    }
    onAdd({
      id: crypto.randomUUID(),
      title,
      visible: true,
      kind: "feature",
      url,
      ...(renderAs ? { renderAs } : {}),
    });
    setFeatureTitle("");
    setFeatureUrl("");
    setFeatureBusy(false);
  }
```

Add the form's JSX, right after the existing "Ajouter un tileset 3D par URL" block (before the closing `</div></div>` that ends the component):

```tsx
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">
          Ajouter une couche par URL GeoJSON
        </p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre de la couche GeoJSON"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={featureTitle}
            onChange={(e) => setFeatureTitle(e.target.value)}
          />
          <input
            aria-label="URL du GeoJSON"
            type="text"
            placeholder="https://…/donnees.geojson"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={featureUrl}
            onChange={(e) => setFeatureUrl(e.target.value)}
          />
          {featureError && (
            <p role="alert" className="text-xs text-amber-600">
              {featureError}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!featureTitle.trim() || !featureUrl.trim() || featureBusy}
            onClick={() => void addFeatureLayer()}
          >
            Ajouter la couche
          </Button>
        </div>
      </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx`
Expected: PASS — all tests, old and new.

- [ ] **Step 5: Run the full shell test suite, type-check, lint**

Run: `cd shell && npm run test && npm run build && npm run lint`
Expected: PASS, no errors.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ajoute une couche carte par URL GeoJSON (LayerPicker)

Formulaire titre+URL, même patron que l'ajout de tileset 3D. Détecte
renderAs depuis la géométrie de la première entité et amorce le cache
d'introspection (geojsonIntrospect.ts) sous la clé que LayersPanel lit,
pour qu'ouvrir la symbologie juste après l'ajout ne refasse pas le
fetch. Échec de la sonde n'empêche pas l'ajout (même trajectoire que le
rendu MapLibre, pas une régression).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: E2E proof and final verification

**Files:**
- Create: `shell/e2e/map-feature-layer-symbology.spec.ts`

**Interfaces:**
- Consumes: `mockCore` from `./mocks` (`shell/e2e/mocks.ts`), the "Nouveau" → dialog → "Créer" map-creation flow already used by `shell/e2e/map-symbology.spec.ts`, the field labels wired in Tasks 2-3 ("Titre de la couche GeoJSON", "URL du GeoJSON", "Ajouter la couche", "Champ couleur", "Recalculer les classes").
- Produces: nothing consumed by later tasks — this is the terminal proof of the plan.

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/map-feature-layer-symbology.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const POI_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { categorie: "banc" },
      geometry: { type: "Point", coordinates: [2.4, 46.6] },
    },
    {
      type: "Feature",
      properties: { categorie: "arbre" },
      geometry: { type: "Point", coordinates: [2.5, 46.7] },
    },
    {
      type: "Feature",
      properties: { categorie: "banc" },
      geometry: { type: "Point", coordinates: [2.6, 46.8] },
    },
  ],
};

// Preuve de sortie SP-28 : une couche ajoutée par une simple URL GeoJSON (pas
// de collection derrière) reçoit une symbologie catégorielle dans l'éditeur
// de cartes — le domaine est calculé depuis l'URL mockée ci-dessous,
// jamais via le cœur (aucune route /aggregate n'est enregistrée ici).
test("add a layer by GeoJSON URL and style it categorically from its own data", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://external.test/poi.geojson", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/geo+json",
      body: JSON.stringify(POI_GEOJSON),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte POI");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Titre de la couche GeoJSON").fill("Points d'intérêt");
  await page.getByLabel("URL du GeoJSON").fill("https://external.test/poi.geojson");
  await page.getByRole("button", { name: "Ajouter la couche" }).click();
  await expect(page.getByText("Points d'intérêt")).toBeVisible();

  await page.getByLabel("Champ couleur").fill("categorie");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText("banc")).toBeVisible();
  await expect(page.getByText("arbre")).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Points d'intérêt")).toBeVisible();
});
```

- [ ] **Step 2: Run the new spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test map-feature-layer-symbology.spec.ts`
Expected: PASS. If a selector doesn't match (e.g. the categorical domain text isn't rendered exactly as `banc`/`arbre` side by side, or the "Nouveau"/dialog flow differs from what Task 2's reading of `map-symbology.spec.ts` assumed), inspect the actual DOM via `npx playwright test map-feature-layer-symbology.spec.ts --debug` and adjust the selector to match reality — never adjust the assertion to something weaker just to make it pass (CLAUDE.md trap #3: verify against the real running app, not the plan's text).

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: PASS. CLAUDE.md's reference count was 111 passed / 4 skipped / 0 failed after SP-27 — expect 112 passed / 4 skipped / 0 failed now (one new spec, one new test). If any other spec now fails, it's almost certainly a `kind: "feature"` fixture somewhere else in `shell/e2e/*.spec.ts` that never expected its layer to be fetched for introspection — find it with `grep -rn 'kind: "feature"' shell/e2e/*.spec.ts` and add a `page.route` for its URL (E2E specs run against a real browser fetch, not MSW — an unmocked E2E fetch to a real "https://fs/..." placeholder URL will simply reject harmlessly, which is fine unless the spec's own assertions depend on the symbology editor's state for that layer).

- [ ] **Step 4: Confirm no OpenAPI/TS regeneration is needed**

Run: `git diff --stat main -- core/app` (or `git diff --stat HEAD~4` if not yet merged) and confirm no `core/app` route or Pydantic model file appears — this plan never touched `core/`. This is the explicit check CLAUDE.md trap #1 asks for; the correct outcome here is "nothing to regenerate," not a skipped step.

- [ ] **Step 5: Run every quality gate from CLAUDE.md's shell section**

Run:

```bash
cd shell
npm run lint && npm run format:check
npm run build
rm -rf dist dist-export
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Expected: all pass, coverage at or above the 88% threshold (run `npm run test -- --coverage` first if `coverage/coverage-summary.json` is missing).

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/e2e/map-feature-layer-symbology.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): E2E — couche par URL GeoJSON stylée en catégoriel (SP-28)

Preuve de sortie : ajouter une couche par URL GeoJSON dans l'éditeur de
cartes, la styliser en catégoriel depuis son propre contenu (aucun
appel /aggregate au cœur), enregistrer, recharger.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes (for the plan author, not a task)

- **Spec coverage:** §2.1 (add-by-URL) → Task 3. §2.2 (module) → Task 1. §2.3 (`LayerSymbologyEditor`) → Task 2. §2.4 (`LayerPopupEditor`) → Task 2. §2.5 (`renderAs` detection) → Task 3. §3.1-3.3 mechanisms → Tasks 1-3 respectively. §4 tests → one task each plus Task 4's E2E. §5 risks are accepted trade-offs, not action items — no task needed.
- **Placeholder scan:** none found — every step has real code, real file paths, real commands.
- **Type consistency:** `fetchFeatureCollection`/`listFields`/`makeStatQueryFn`/`makeSampleFieldFn` are named and typed identically across Task 1 (definition), Task 2 (`LayersPanel.tsx` consumption), and Task 3 (`LayerPicker.tsx` consumption). The react-query key `["feature-geojson", url]` is the same literal array shape in both Task 2 (read) and Task 3 (write via `setQueryData`).
