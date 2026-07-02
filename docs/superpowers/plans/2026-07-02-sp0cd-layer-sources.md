# GeoStudio SP-0c-d — Sources de couches & LayerPicker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the map editor discover addable layers from the platform tile services — aggregate Martin (`/catalog`, vector) and pg_featureserv (`/collections`, features) into a `LayerSource[]` behind the `item-client`, expose it via `useLayerSources`, and render a `LayerPicker` that emits a ready-to-use `MapLayer` on selection.

**Architecture:** All service access stays inside the `item-client` façade — `createItemClient` gains `martinUrl`/`featureservUrl` opts (from `VITE_MARTIN_URL`/`VITE_FEATURESERV_URL`), and `listLayerSources()` fetches both catalogs with `Promise.allSettled` (resilient: one service down still yields the other; both down throws). A TanStack Query hook wraps it; `LayerPicker` lists sources and, on click, builds the correct `MapLayer` (vector→tiles+sourceLayer, feature→GeoJSON url) with a fresh unique id. No new backend.

**Tech Stack:** React 19, TypeScript, Vite 6, Vitest 3 + Testing Library + MSW, TanStack Query.

## Global Constraints

- Front: ALL network access via `item-client`; no service URL hard-coded anywhere else — Martin/featureserv URLs come only from `VITE_*` env and are passed into `createItemClient`.
- `Item`/`ItemClient`/`MapConfig` contracts extended by addition only; existing tests stay green.
- No token in localStorage (unchanged).
- Martin `/catalog` and pg_featureserv `/collections` payload shapes are best-effort, confined to the façade and defined by the mocks (spec §12) — adjust against real services later.
- MSW `onUnhandledRequest: "error"` — every fetched URL must have a handler in tests.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev` (do not branch or merge here).
- `MapLayer` discriminated union already exists in `shell/src/api/types.ts` (vector/raster/feature/deck).

---

### Task 1: `LayerSource` type + `listLayerSources` in the item-client

**Files:**
- Modify: `shell/src/api/types.ts` (add `LayerSource`; extend `ItemClient`)
- Modify: `shell/src/api/itemClient.ts` (add `martinUrl`/`featureservUrl` opts + `listLayerSources`)
- Modify: `shell/src/config.ts` (surface `martinUrl`/`featureservUrl` from env)
- Modify: `shell/src/App.tsx` (pass the two URLs into `createItemClient`)
- Test: `shell/src/api/itemClient.test.ts` (MSW tests for `listLayerSources`)
- Check: `shell/src/config.test.ts` (if it asserts the returned shape, extend it)

**Interfaces:**
- Consumes: existing `createItemClient(opts)`, `AppConfig`, MSW `server` from `../test/msw/server`.
- Produces:
  - `type LayerSource = { id: string; title: string; service: "martin" | "featureserv"; kind: "vector" | "feature"; tilesUrl?: string; sourceLayer?: string; url?: string }`
  - `ItemClient.listLayerSources(): Promise<LayerSource[]>`
  - `createItemClient` opts gain `martinUrl?: string` and `featureservUrl?: string`.
  - `AppConfig` gains `martinUrl: string` and `featureservUrl: string` (default `""` when unset).

- [ ] **Step 1: Add the `LayerSource` type and extend `ItemClient`**

Edit `shell/src/api/types.ts`. After the `MapConfig` type, add:

```ts
export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "featureserv";
  kind: "vector" | "feature";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
};
```

In the `ItemClient` interface, add the method (after `setSharing`):

```ts
  listLayerSources(): Promise<LayerSource[]>;
```

- [ ] **Step 2: Write the failing MSW tests**

Edit `shell/src/api/itemClient.test.ts`. Update the `makeClient` helper to pass the two new URLs (keep existing callers working — the params are optional, so only add them here):

```ts
function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    martinUrl: "https://martin.test",
    featureservUrl: "https://featureserv.test",
    getToken: () => token,
  });
}
```

Add these tests at the end of the file (import `http`, `HttpResponse`, `server` are already imported at the top):

```ts
test("listLayerSources aggregates Martin vector sources and featureserv collections", async () => {
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { content_type: "application/x-protobuf", description: "Communes" },
          routes: { content_type: "application/x-protobuf" },
        },
      }),
    ),
    http.get("https://featureserv.test/collections.json", () =>
      HttpResponse.json({
        collections: [{ id: "public.parcs", title: "Parcs" }],
      }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  const martin = sources.find((s) => s.id === "communes");
  expect(martin).toMatchObject({
    title: "Communes",
    service: "martin",
    kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  // Martin source without a description falls back to its id for the title.
  expect(sources.find((s) => s.id === "routes")?.title).toBe("routes");
  const feature = sources.find((s) => s.id === "public.parcs");
  expect(feature).toMatchObject({
    title: "Parcs",
    service: "featureserv",
    kind: "feature",
    url: "https://featureserv.test/collections/public.parcs/items.json",
  });
});

test("listLayerSources still returns one service when the other fails", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://featureserv.test/collections.json", () =>
      HttpResponse.json({ collections: [{ id: "public.parcs", title: "Parcs" }] }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources).toHaveLength(1);
  expect(sources[0].service).toBe("featureserv");
});

test("listLayerSources throws when both services fail", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://featureserv.test/collections.json", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(makeClient().listLayerSources()).rejects.toThrow();
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `listLayerSources` is not implemented (type error / not a function).

- [ ] **Step 4: Implement `listLayerSources` and the new opts**

Edit `shell/src/api/itemClient.ts`. Update the imports to include `LayerSource`:

```ts
import type { CreateKind, Group, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, Me, ResourceType, Sharing, UpdatePatch } from "./types";
```

Extend the opts type and destructuring:

```ts
export function createItemClient(opts: {
  geonodeUrl: string;
  builderUrl: string;
  martinUrl?: string;
  featureservUrl?: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { geonodeUrl, builderUrl, martinUrl, featureservUrl, getToken } = opts;
```

Add these two private helpers inside `createItemClient` (after the existing `get` helper), then the method in the returned object (add after `setSharing`):

```ts
  async function fetchMartinSources(): Promise<LayerSource[]> {
    if (!martinUrl) return [];
    const res = await fetch(`${martinUrl}/catalog`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /catalog`);
    const data = (await res.json()) as {
      tiles?: Record<string, { description?: string }>;
    };
    return Object.entries(data.tiles ?? {}).map(([id, meta]) => ({
      id,
      title: meta.description ?? id,
      service: "martin" as const,
      kind: "vector" as const,
      tilesUrl: `${martinUrl}/${id}/{z}/{x}/{y}`,
      sourceLayer: id,
    }));
  }

  async function fetchFeatureservSources(): Promise<LayerSource[]> {
    if (!featureservUrl) return [];
    const res = await fetch(`${featureservUrl}/collections.json`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections.json`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "featureserv" as const,
      kind: "feature" as const,
      url: `${featureservUrl}/collections/${c.id}/items.json`,
    }));
  }
```

```ts
    async listLayerSources(): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(),
        fetchFeatureservSources(),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS — the three new tests plus all existing item-client tests.

- [ ] **Step 6: Surface the URLs through config and App wiring**

Edit `shell/src/config.ts`. Add to `AppConfig`:

```ts
  martinUrl: string;
  featureservUrl: string;
```

And in the returned object of `loadConfig` (these are optional — no `required` entry):

```ts
    martinUrl: env.VITE_MARTIN_URL ?? "",
    featureservUrl: env.VITE_FEATURESERV_URL ?? "",
```

Edit `shell/src/App.tsx` — pass them into `createItemClient`:

```ts
      createItemClient({
        geonodeUrl: config.geonodeUrl,
        builderUrl: config.builderUrl,
        martinUrl: config.martinUrl,
        featureservUrl: config.featureservUrl,
        getToken: getAccessToken,
      }),
```

- [ ] **Step 7: Keep config tests green**

Run: `cd shell && npx vitest run src/config.test.ts`
Expected: PASS. If `config.test.ts` asserts the full returned object with `toEqual`, add `martinUrl: ""`/`featureservUrl: ""` to its expectation; if it uses `toMatchObject`, no change needed.

- [ ] **Step 8: Full suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; `tsc --noEmit && vite build` succeeds.

- [ ] **Step 9: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/config.ts shell/src/config.test.ts shell/src/App.tsx
git commit -m "feat(shell): aggregate Martin + featureserv layer sources in item-client

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `useLayerSources` hook + `LayerPicker` component

**Files:**
- Modify: `shell/src/api/hooks.ts` (add `useLayerSources`)
- Create: `shell/src/map/LayerPicker.tsx`
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `useItemClient`, `LayerSource`/`MapLayer` from `../api/types`, `listLayerSources`.
- Produces:
  - `useLayerSources(opts?: { enabled?: boolean })` → `useQuery(["layer-sources"], () => client.listLayerSources())`.
  - `LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void })` — lists sources; clicking one calls `onAdd` with a constructed `MapLayer` (vector or feature) carrying a fresh unique id.

- [ ] **Step 1: Add the `useLayerSources` hook**

Edit `shell/src/api/hooks.ts`. It already imports from `./types`; there is nothing new to import for the hook itself. Add:

```ts
export function useLayerSources(options?: { enabled?: boolean }) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["layer-sources"],
    queryFn: () => client.listLayerSources(),
    enabled: options?.enabled ?? true,
  });
}
```

- [ ] **Step 2: Write the failing LayerPicker test**

Create `shell/src/map/LayerPicker.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, LayerSource, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayerPicker } from "./LayerPicker";

const sources: LayerSource[] = [
  { id: "communes", title: "Communes", service: "martin", kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}", sourceLayer: "communes" },
  { id: "public.parcs", title: "Parcs", service: "featureserv", kind: "feature",
    url: "https://fs.test/collections/public.parcs/items.json" },
];

function renderPicker(onAdd: (l: MapLayer) => void) {
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("lists sources and emits a vector MapLayer on click", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "vector",
    title: "Communes",
    visible: true,
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("emits a feature MapLayer for a featureserv source", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.click(await screen.findByRole("button", { name: /Parcs/ }));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Parcs",
    visible: true,
    url: "https://fs.test/collections/public.parcs/items.json",
  });
});

test("gives each added layer a distinct id", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  await userEvent.click(btn);
  const id1 = (onAdd.mock.calls[0][0] as MapLayer).id;
  const id2 = (onAdd.mock.calls[1][0] as MapLayer).id;
  expect(id1).not.toBe(id2);
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx`
Expected: FAIL — `./LayerPicker` does not exist.

- [ ] **Step 4: Implement `LayerPicker`**

Create `shell/src/map/LayerPicker.tsx`:

```tsx
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
    };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const { data, isLoading, isError, refetch } = useLayerSources();

  if (isLoading) return <p className="text-sm text-slate-500">Chargement des sources…</p>;
  if (isError) {
    return (
      <div className="text-sm text-red-600">
        <p role="alert">Impossible de charger les sources de couches.</p>
        <button type="button" className="underline" onClick={() => refetch()}>
          Réessayer
        </button>
      </div>
    );
  }
  if (!data || data.length === 0) {
    return <p className="text-sm text-slate-500">Aucune source disponible.</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {data.map((source) => (
        <li key={`${source.service}:${source.id}`}>
          <button
            type="button"
            className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
            onClick={() => onAdd(toMapLayer(source))}
          >
            {source.title}
            <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx`
Expected: PASS — all three tests.

- [ ] **Step 6: Full suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "feat(shell): add useLayerSources hook and LayerPicker component

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (§4, §5, §6, §10 0c-d):** `martinUrl`/`featureservUrl` opts + env (§4) → Task 1 Steps 4,6. `LayerSource` type + `listLayerSources` aggregating Martin `/catalog` + pg_featureserv `/collections` (§4) → Task 1. `useLayerSources` (§6) + `LayerPicker` building the `MapLayer` (§5) → Task 2. Resilience/error state (§8) → Task 1 `allSettled` + Task 2 error branch with retry. TiTiler/raster explicitly out of 0c-d (§4) — not built.
- **Placeholder scan:** none — all steps carry concrete code and commands.
- **Type consistency:** `LayerSource` shape identical in types.ts, item-client, tests, and `toMapLayer`; `listLayerSources` signature matches across interface/impl/hook; `MapLayer` vector/feature variants match `types.ts`. Martin URL uses `/catalog`, featureserv uses `/collections.json` consistently in impl and tests (MSW would error on any unhandled URL, catching drift).
- **Best-effort shapes:** Martin `tiles` map and featureserv `collections` array are mock-defined per §12; noted for real-service adjustment.
