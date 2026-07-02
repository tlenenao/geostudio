# GeoStudio SP-0c-e — Éditeur de carte & intégration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the full map editor: create a `kind="map"` item, load/edit its `MapConfig` (basemap + layers + view), and save it — wired into the shell (new "Map" type, `/maps/:pk` route, open-from-catalog), backed by a builder `PUT /configs/by-item/{id}` and validated by a real-render Playwright E2E.

**Architecture:** Backend gains `PUT /configs/by-item/{item_id}` (reusing `get_config_by_item` + `update_config`, mirroring the existing DELETE-by-item). The `item-client` gains `createMapItem`/`getMapConfig`/`saveMapConfig` (all builder-only, mapping the flat builder `MapConfig` to/from the frontend discriminated `MapLayer`). Hooks wrap them. `BasemapSelect` and `LayersPanel` (reorder/toggle/remove + embedded `LayerPicker`) are pure editing widgets; `MapEditorPage` composes them with `MapView` over local state and a Save button. Routing adds `/maps/:pk` and routes map items there. Finally `MapView` absorbs its two deferred hardening items (per-layer try/catch isolation; `isStyleLoaded()` guard).

**Tech Stack:** Python 3.12+/FastAPI/pytest (backend); React 19 + TS + Vite 6 + Vitest 3 + Testing Library + MSW + Playwright (frontend); MapLibre/Deck.gl mocked in unit, real in E2E.

## Global Constraints

- Front: ALL network via `item-client`; no service URL hard-coded (basemap **style URLs** are app data defined in one `basemaps.ts` module, not platform-service endpoints).
- Builder contract extended by ADDITION only (new `PUT /configs/by-item/{id}`); existing app/dashboard/map endpoints unchanged.
- `Item`/`ItemClient`/`MapConfig` extended by addition; existing tests stay green.
- MapLibre/Deck.gl mocked in unit; real render only in E2E. A single layer error must never break the whole map (isolation).
- No token in localStorage. MSW `onUnhandledRequest:"error"`.
- pytest `filterwarnings=["error"]` with the two authorized ignores already in `pyproject.toml`; in-memory sqlite fixtures use `engine.dispose()` + `StaticPool`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`.
- France skeleton view = `center: [2.4, 46.6], zoom: 5`. Builder `MapConfig` model (flat `MapLayer` superset) already exists in `builder-service/app/schemas.py`; frontend discriminated `MapLayer`/`MapConfig` in `shell/src/api/types.ts`.

---

### Task 1: Backend `PUT /configs/by-item/{item_id}`

**Files:**
- Modify: `builder-service/app/routes.py`
- Test: `builder-service/tests/test_routes.py` (append; match existing test style/fixtures)

**Interfaces:**
- Consumes: `repo.get_config_by_item(session, item_id)`, `repo.update_config(session, config_id, config)`, `BuilderConfig`.
- Produces: `PUT /configs/by-item/{item_id}` → 200 `ConfigRead` (new revision) or 404 if no config for that item.

- [ ] **Step 1: Write the failing test**

Append to `builder-service/tests/test_routes.py` (reuse the module's existing `client` fixture and the helper that POSTs a map config; if the map round-trip test already builds a map config body, mirror it):

```python
def test_put_config_by_item_updates_map(client):
    # Create a map item via the normal flow.
    create = client.post(
        "/configs",
        json={
            "title": "Ma carte",
            "owner": "alice",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [2.4, 46.6], "zoom": 5},
                    "layers": [],
                },
            },
        },
    )
    assert create.status_code == 201
    item_id = create.json()["itemId"]

    # Update it by item id.
    put = client.put(
        f"/configs/by-item/{item_id}",
        json={
            "kind": "map",
            "map": {
                "basemap": {"style": "https://demo/style.json"},
                "view": {"center": [1.0, 47.0], "zoom": 8},
                "layers": [
                    {"id": "a", "title": "A", "visible": True, "kind": "feature",
                     "url": "https://fs/a"}
                ],
            },
        },
    )
    assert put.status_code == 200
    body = put.json()
    # ConfigRead nests the builder config under "config"; the map payload is config.map.
    assert body["config"]["map"]["view"]["zoom"] == 8
    assert len(body["config"]["map"]["layers"]) == 1

    # Confirm persistence via GET by-item.
    got = client.get(f"/configs/by-item/{item_id}")
    assert got.json()["config"]["map"]["layers"][0]["id"] == "a"


def test_put_config_by_item_404_when_missing(client):
    resp = client.put(
        "/configs/by-item/does-not-exist",
        json={"kind": "map", "map": {
            "basemap": {"style": "s"}, "view": {"center": [0, 0], "zoom": 1}, "layers": []}},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd builder-service && uv run pytest tests/test_routes.py -k put_config_by_item -v`
Expected: FAIL — 405/404 route not found (PUT by-item unimplemented).

- [ ] **Step 3: Implement the route**

Edit `builder-service/app/routes.py`. Add after `get_config_by_item` (before or after `delete_config_by_item`):

```python
@router.put("/configs/by-item/{item_id}", response_model=ConfigRead)
def update_config_by_item(
    item_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
) -> ConfigRead:
    existing = repo.get_config_by_item(session, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="config not found")
    result = repo.update_config(session, existing.id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd builder-service && uv run pytest tests/test_routes.py -k put_config_by_item -v`
Expected: PASS (both).

- [ ] **Step 5: Full backend suite**

Run: `cd builder-service && uv run pytest`
Expected: all pass, no warnings-as-errors.

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/routes.py builder-service/tests/test_routes.py
git commit -m "feat(builder): add PUT /configs/by-item/{id} for map saves

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: item-client `createMapItem` / `getMapConfig` / `saveMapConfig` + basemaps

**Files:**
- Create: `shell/src/map/basemaps.ts`
- Modify: `shell/src/api/types.ts` (extend `ItemClient`)
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `builderUrl`, `getToken`, `MapConfig`/`MapLayer`, `POST /configs` and `GET`/`PUT /configs/by-item/{id}`.
- Produces on `ItemClient`:
  - `createMapItem(input: { title: string; owner: string }): Promise<Item>`
  - `getMapConfig(pk: string): Promise<MapConfig>`
  - `saveMapConfig(pk: string, config: MapConfig): Promise<void>`
  - `basemaps.ts` exports `BASEMAPS: { id: string; label: string; style: string }[]` and `DEFAULT_BASEMAP = BASEMAPS[0]`.

- [ ] **Step 1: Create the basemap catalogue**

Create `shell/src/map/basemaps.ts`:

```ts
export type Basemap = { id: string; label: string; style: string };

export const BASEMAPS: Basemap[] = [
  { id: "clair", label: "Clair", style: "https://demotiles.maplibre.org/style.json" },
  { id: "positron", label: "Positron", style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" },
  { id: "voyager", label: "Voyager", style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json" },
];

export const DEFAULT_BASEMAP: Basemap = BASEMAPS[0];
```

- [ ] **Step 2: Extend the `ItemClient` interface**

Edit `shell/src/api/types.ts`, add to `ItemClient` (after `listLayerSources`):

```ts
  createMapItem(input: { title: string; owner: string }): Promise<Item>;
  getMapConfig(pk: string): Promise<MapConfig>;
  saveMapConfig(pk: string, config: MapConfig): Promise<void>;
```

- [ ] **Step 3: Write the failing MSW tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("createMapItem posts a map skeleton and returns a map Item", async () => {
  let body: any;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: "map", itemId: "77" }, { status: 201 });
    }),
  );
  const item = await makeClient().createMapItem({ title: "Carte", owner: "alice" });
  expect(body.config.kind).toBe("map");
  expect(body.config.map.layers).toEqual([]);
  expect(item).toMatchObject({ pk: "77", resourceType: "map", title: "Carte", configId: "cfg-1" });
});

test("getMapConfig reads and maps the builder map config", async () => {
  // ConfigRead nests the builder config under "config"; the map is config.map.
  server.use(
    http.get("https://builder.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1", itemId: "77", kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              { id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a",
                tilesUrl: null, sourceLayer: null, opacity: null, deckType: null, dataUrl: null, paint: null, props: null },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.zoom).toBe(8);
  expect(cfg.layers[0]).toEqual({ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" });
});

test("getMapConfig throws when the config has no map payload", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/77", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "app", config: { kind: "app", map: null } }),
    ),
  );
  await expect(makeClient().getMapConfig("77")).rejects.toThrow();
});

test("saveMapConfig PUTs the map config by item", async () => {
  let method = ""; let body: any;
  server.use(
    http.put("https://builder.test/configs/by-item/77", async ({ request }) => {
      method = request.method; body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "map", map: body.map });
    }),
  );
  const cfg = { basemap: { style: "s" }, view: { center: [0, 0] as [number, number], zoom: 3 }, layers: [] };
  await makeClient().saveMapConfig("77", cfg);
  expect(method).toBe("PUT");
  expect(body.kind).toBe("map");
  expect(body.map.view.zoom).toBe(3);
});
```

- [ ] **Step 4: Run to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — the three methods are not implemented.

- [ ] **Step 5: Implement the three methods**

Edit `shell/src/api/itemClient.ts`. Add `MapConfig`/`MapLayer` to the type import, and import the default basemap:

```ts
import type { CreateKind, Group, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, ResourceType, Sharing, UpdatePatch } from "./types";
import { DEFAULT_BASEMAP } from "../map/basemaps";
```

Add a raw-layer mapper near `toItem` (module scope):

```ts
type RawMapLayer = {
  id: string; title: string; visible: boolean; kind: string;
  tilesUrl?: string | null; sourceLayer?: string | null; url?: string | null;
  opacity?: number | null; deckType?: string | null; dataUrl?: string | null;
  paint?: Record<string, unknown> | null; props?: Record<string, unknown> | null;
};

function toFrontLayer(l: RawMapLayer): MapLayer {
  const base = { id: l.id, title: l.title, visible: l.visible };
  switch (l.kind) {
    case "vector":
      return { ...base, kind: "vector", tilesUrl: l.tilesUrl ?? "", sourceLayer: l.sourceLayer ?? "",
        ...(l.paint ? { paint: l.paint } : {}) };
    case "raster":
      return { ...base, kind: "raster", tilesUrl: l.tilesUrl ?? "",
        ...(l.opacity != null ? { opacity: l.opacity } : {}) };
    case "deck":
      return { ...base, kind: "deck", deckType: (l.deckType ?? "heatmap") as "heatmap" | "hexbin" | "column",
        dataUrl: l.dataUrl ?? "", ...(l.props ? { props: l.props } : {}) };
    case "feature":
    default:
      return { ...base, kind: "feature", url: l.url ?? "", ...(l.paint ? { paint: l.paint } : {}) };
  }
}
```

Add the three methods to the returned client object (after `listLayerSources`). Note `createMapItem` reuses the same POST shape as `createConfigItem`:

```ts
    async createMapItem(input: { title: string; owner: string }): Promise<Item> {
      const map: MapConfig = {
        basemap: { style: DEFAULT_BASEMAP.style },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
      const config = { version: 1, kind: "map", map };
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ title: input.title, owner: input.owner, config }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /configs`);
      const data = (await res.json()) as { id: string | number; kind: string; itemId: string | null };
      if (!data.itemId) throw new Error("createMapItem: builder returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "map", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
      };
    },

    async getMapConfig(pk: string): Promise<MapConfig> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} GET /configs/by-item/${pk}`);
      // ConfigRead nests the builder config under "config"; the map is config.map.
      const data = (await res.json()) as {
        config?: { map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null };
      };
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
      };
    },

    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ version: 1, kind: "map", map: config }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} PUT /configs/by-item/${pk}`);
    },
```

- [ ] **Step 6: Run to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 7: Full suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 8: Commit**

```bash
git add shell/src/map/basemaps.ts shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add createMapItem/getMapConfig/saveMapConfig + basemap catalogue

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Map hooks — `useCreateMap` / `useMapConfig` / `useSaveMap`

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx` (append; if absent, create following the LayerPicker test's provider setup)

**Interfaces:**
- Consumes: `useItemClient`, `createMapItem`/`getMapConfig`/`saveMapConfig`, `MapConfig`.
- Produces:
  - `useCreateMap()` → mutation of `createMapItem`; `onSuccess` invalidates `["items"]`.
  - `useMapConfig(pk, opts?)` → query `["map", pk]`.
  - `useSaveMap(pk)` → mutation of `saveMapConfig`; `onSuccess` invalidates `["map", pk]`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/api/hooks.test.tsx` (use the file's existing `renderHook`/wrapper helper; if the file does not exist, create it with a wrapper that provides `QueryClientProvider` + `ItemClientProvider` around a `vi.fn`-based mock `ItemClient`, mirroring `LayerPicker.test.tsx`):

```tsx
test("useCreateMap creates a map and invalidates items", async () => {
  const client = {
    createMapItem: vi.fn().mockResolvedValue({ pk: "77", resourceType: "map", title: "C" }),
  } as unknown as ItemClient;
  const { result } = renderHook(() => useCreateMap(), { wrapper: makeWrapper(client) });
  await result.current.mutateAsync({ title: "C", owner: "alice" });
  expect(client.createMapItem).toHaveBeenCalledWith({ title: "C", owner: "alice" });
});

test("useMapConfig loads a map config", async () => {
  const cfg = { basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [] };
  const client = { getMapConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useMapConfig("77"), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual(cfg);
  expect(client.getMapConfig).toHaveBeenCalledWith("77");
});

test("useSaveMap saves a map config", async () => {
  const client = { saveMapConfig: vi.fn().mockResolvedValue(undefined) } as unknown as ItemClient;
  const { result } = renderHook(() => useSaveMap("77"), { wrapper: makeWrapper(client) });
  const cfg = { basemap: { style: "s" }, view: { center: [0, 0] as [number, number], zoom: 1 }, layers: [] };
  await result.current.mutateAsync(cfg);
  expect(client.saveMapConfig).toHaveBeenCalledWith("77", cfg);
});
```

(If creating the file, add imports: `renderHook`, `waitFor` from `@testing-library/react`; `QueryClient`, `QueryClientProvider`; `expect`, `test`, `vi`; `ItemClientProvider`; the hooks; `ItemClient` type. Define `makeWrapper(client)` returning a component that nests the two providers with a `retry:false` QueryClient.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/api/hooks.test.tsx`
Expected: FAIL — hooks not exported.

- [ ] **Step 3: Implement the hooks**

Edit `shell/src/api/hooks.ts`. Add `MapConfig` to the type import from `./types`, then add:

```ts
export function useCreateMap() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string }) => client.createMapItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useMapConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["map", pk],
    queryFn: () => client.getMapConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveMap(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: MapConfig) => client.saveMapConfig(pk, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["map", pk] });
    },
  });
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd shell && npx vitest run src/api/hooks.test.tsx`
Expected: PASS.

- [ ] **Step 5: Full suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): add useCreateMap/useMapConfig/useSaveMap hooks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `BasemapSelect` + `LayersPanel` widgets

**Files:**
- Create: `shell/src/map/BasemapSelect.tsx`, `shell/src/map/LayersPanel.tsx`
- Test: `shell/src/map/BasemapSelect.test.tsx`, `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `BASEMAPS` from `./basemaps`, `MapLayer`/`MapConfig` from `../api/types`, `LayerPicker` from `./LayerPicker`.
- Produces:
  - `BasemapSelect({ value, onChange }: { value: string; onChange: (style: string) => void })` — `<select>` over `BASEMAPS`.
  - `LayersPanel({ layers, onChange }: { layers: MapLayer[]; onChange: (layers: MapLayer[]) => void })` — per layer: toggle visible, move up/down, remove; embeds `LayerPicker` (`onAdd` appends).

- [ ] **Step 1: Write the failing BasemapSelect test**

Create `shell/src/map/BasemapSelect.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { BASEMAPS } from "./basemaps";
import { BasemapSelect } from "./BasemapSelect";

test("shows the current basemap and reports changes as a style url", async () => {
  const onChange = vi.fn();
  render(<BasemapSelect value={BASEMAPS[0].style} onChange={onChange} />);
  const select = screen.getByLabelText("Fond de carte") as HTMLSelectElement;
  expect(select.value).toBe(BASEMAPS[0].style);
  await userEvent.selectOptions(select, BASEMAPS[1].style);
  expect(onChange).toHaveBeenCalledWith(BASEMAPS[1].style);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/map/BasemapSelect.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 3: Implement `BasemapSelect`**

Create `shell/src/map/BasemapSelect.tsx`:

```tsx
import { BASEMAPS } from "./basemaps";

export function BasemapSelect({ value, onChange }: { value: string; onChange: (style: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      Fond de carte
      <select
        aria-label="Fond de carte"
        className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {BASEMAPS.map((b) => (
          <option key={b.id} value={b.style}>{b.label}</option>
        ))}
      </select>
    </label>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/map/BasemapSelect.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing LayersPanel test**

Create `shell/src/map/LayersPanel.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayersPanel } from "./LayersPanel";

const layers: MapLayer[] = [
  { id: "a", title: "A", visible: true, kind: "feature", url: "u1" },
  { id: "b", title: "B", visible: true, kind: "feature", url: "u2" },
];

function renderPanel(current: MapLayer[], onChange: (l: MapLayer[]) => void) {
  const client = { listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={current} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("toggles a layer's visibility", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Masquer A" }));
  expect(onChange).toHaveBeenCalledWith([
    { ...layers[0], visible: false }, layers[1],
  ]);
});

test("removes a layer", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Retirer A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1]]);
});

test("moves a layer down", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Descendre A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1], layers[0]]);
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 7: Implement `LayersPanel`**

Create `shell/src/map/LayersPanel.tsx`:

```tsx
import type { MapLayer } from "../api/types";
import { LayerPicker } from "./LayerPicker";

export function LayersPanel({
  layers,
  onChange,
}: {
  layers: MapLayer[];
  onChange: (layers: MapLayer[]) => void;
}) {
  function toggle(id: string) {
    onChange(layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));
  }
  function remove(id: string) {
    onChange(layers.filter((l) => l.id !== id));
  }
  function move(index: number, delta: number) {
    const next = index + delta;
    if (next < 0 || next >= layers.length) return;
    const copy = [...layers];
    [copy[index], copy[next]] = [copy[next], copy[index]];
    onChange(copy);
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1">
        {layers.map((layer, i) => (
          <li key={layer.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">{layer.title}</span>
            <button type="button" aria-label={`Monter ${layer.title}`} disabled={i === 0}
              className="px-1 disabled:opacity-30" onClick={() => move(i, -1)}>↑</button>
            <button type="button" aria-label={`Descendre ${layer.title}`} disabled={i === layers.length - 1}
              className="px-1 disabled:opacity-30" onClick={() => move(i, 1)}>↓</button>
            <button type="button" aria-label={`${layer.visible ? "Masquer" : "Afficher"} ${layer.title}`}
              className="px-1" onClick={() => toggle(layer.id)}>{layer.visible ? "👁" : "🚫"}</button>
            <button type="button" aria-label={`Retirer ${layer.title}`}
              className="px-1 text-red-600" onClick={() => remove(layer.id)}>✕</button>
          </li>
        ))}
        {layers.length === 0 && <li className="text-xs text-slate-400">Aucune couche.</li>}
      </ul>
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter une couche</p>
        <LayerPicker onAdd={(layer) => onChange([...layers, layer])} />
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx src/map/BasemapSelect.test.tsx`
Expected: PASS.

- [ ] **Step 9: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/map/BasemapSelect.tsx shell/src/map/BasemapSelect.test.tsx shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "feat(shell): add BasemapSelect and LayersPanel editing widgets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `MapEditorPage`

**Files:**
- Create: `shell/src/pages/MapEditorPage.tsx`
- Test: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `useMapConfig`/`useSaveMap`, `MapView`, `LayersPanel`, `BasemapSelect`, `MapConfig`/`MapLayer`, `Button`. The `maplibre-gl`/`@deck.gl/*` mocks are required in the test (MapView renders a map).
- Produces: `MapEditorPage({ pk }: { pk: string })` — loads config into local state; `MapView` `onViewChange` updates `view`; `LayersPanel`/`BasemapSelect` update state; **Enregistrer** calls `useSaveMap`; loading/error/save-error states.

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/MapEditorPage.test.tsx` (mock the map libs exactly as `MapView.test.tsx` does — copy the three `vi.mock` blocks and the `overlayInstances`/`mapInstances` resets):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, MapConfig } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { mapInstances } from "../test/MockMaplibreMap";
import { overlayInstances } from "../test/MockDeckgl";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});
vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});
vi.mock("@deck.gl/aggregation-layers", async () => {
  const { HeatmapLayer, HexagonLayer } = await import("../test/MockDeckgl");
  return { HeatmapLayer, HexagonLayer };
});
vi.mock("@deck.gl/layers", async () => {
  const { ColumnLayer } = await import("../test/MockDeckgl");
  return { ColumnLayer };
});

const { MapEditorPage } = await import("./MapEditorPage");

beforeEach(() => {
  mapInstances.length = 0;
  overlayInstances.length = 0;
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.4, 46.6], zoom: 5 },
  layers: [{ id: "a", title: "Couche A", visible: true, kind: "feature", url: "u" }],
};

function renderEditor(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MapEditorPage pk="77" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("loads the config and saves edits", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Retirer Couche A" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const savedLayers = saveMapConfig.mock.calls[0][1].layers;
  expect(savedLayers).toEqual([]);
});

test("shows an error when loading fails", async () => {
  renderEditor({ getMapConfig: vi.fn().mockRejectedValue(new Error("boom")) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/carte introuvable/i);
});

test("surfaces a save failure", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig: vi.fn().mockRejectedValue(new Error("nope")),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText(/échec de l'enregistrement/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx`
Expected: FAIL — page missing.

- [ ] **Step 3: Implement `MapEditorPage`**

Create `shell/src/pages/MapEditorPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useMapConfig, useSaveMap } from "../api/hooks";
import type { MapConfig, MapLayer } from "../api/types";
import { MapView } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { Button } from "../ui/button";

export function MapEditorPage({ pk }: { pk: string }) {
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);

  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);

  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return (
      <p role="alert" className="text-sm text-red-600">
        Carte introuvable.
      </p>
    );

  const setLayers = (layers: MapLayer[]) => setDraft({ ...draft, layers });
  const setStyle = (style: string) => setDraft({ ...draft, basemap: { style } });
  const setView = (view: { center: [number, number]; zoom: number }) =>
    setDraft((d) => (d ? { ...d, view } : d));

  return (
    <div className="flex h-full gap-4">
      <aside className="flex w-72 flex-col gap-4 overflow-auto">
        <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
        <LayersPanel layers={draft.layers} onChange={setLayers} />
        <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
          Enregistrer
        </Button>
        {save.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de l'enregistrement.
          </p>
        )}
      </aside>
      <div className="relative flex-1">
        <MapView config={draft} onViewChange={setView} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx`
Expected: PASS (all three).

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): add MapEditorPage composing MapView + editing panels

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Shell integration + MapView hardening

**Files:**
- Modify: `shell/src/shell/routes.tsx`, `shell/src/pages/CatalogPage.tsx`, `shell/src/ui/ItemCard.tsx`, `shell/src/pages/ItemDetailPage.tsx`, `shell/src/shell/NewItemButton.tsx`
- Modify: `shell/src/map/MapView.tsx`, `shell/src/test/MockMaplibreMap.ts`
- Test: `shell/src/shell/NewItemButton.test.tsx` (append), `shell/src/map/MapView.test.tsx` (append), existing catalog/detail tests kept green

**Interfaces:**
- Consumes: `useCreateMap`, `MapEditorPage`, existing open-item flow, `ResourceType`.
- Produces: `/maps/:pk` route; map items open into the editor; "Map" option in `NewItemButton`; `applyLayers` isolates per-layer failures; the `[config.layers]` effect guards on `map.isStyleLoaded()`.

- [ ] **Step 1: Write failing tests (routing type + NewItemButton Map + MapView isolation)**

(a) Extend `shell/src/test/MockMaplibreMap.ts` first so the isolation test can force a throw and the style guard exists — add a `throwOnAddLayer: Set<string>` field and `isStyleLoaded()`:

```ts
  throwOnAddLayer = new Set<string>();
  isStyleLoaded() {
    return true;
  }
```

and in `addLayer`, throw when targeted (place at the top of the method):

```ts
    if (this.throwOnAddLayer.has(layer.id)) throw new Error(`boom ${layer.id}`);
```

(b) Append to `shell/src/map/MapView.test.tsx`:

```ts
test("isolates a failing layer and still renders the others", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "ok1", title: "OK1", visible: true, kind: "feature", url: "u1" },
      { id: "bad", title: "BAD", visible: true, kind: "feature", url: "u2" },
      { id: "ok2", title: "OK2", visible: true, kind: "feature", url: "u3" },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("bad");
  // Re-apply by firing load again is not needed; assert the initial apply isolated it.
  expect(map.getLayer("ok1")).toBeDefined();
  expect(map.getLayer("ok2")).toBeDefined();
});
```

NOTE: because the mock fires `load` synchronously during `new Map(...)`, set `throwOnAddLayer` is too late for the first apply. Instead, seed it via a config re-apply: change the test to render an empty config first is unnecessary — simplest reliable form: add the id to a shared set the mock reads. Implement the test as: render with the bad layer, then trigger a re-apply through a rerender that keeps `bad` and toggles nothing. To keep it deterministic, use this form instead:

```ts
test("isolates a failing layer and still renders the others", () => {
  const good1: MapLayer = { id: "ok1", title: "OK1", visible: true, kind: "feature", url: "u1" };
  const bad: MapLayer = { id: "bad", title: "BAD", visible: true, kind: "feature", url: "u2" };
  const good2: MapLayer = { id: "ok2", title: "OK2", visible: true, kind: "feature", url: "u3" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good1] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("bad");
  rerender(<MapView config={{ ...config, layers: [good1, bad, good2] }} />);
  expect(map.getLayer("ok1")).toBeDefined();
  expect(map.getLayer("ok2")).toBeDefined();
  expect(map.getLayer("bad")).toBeUndefined();
});
```

Add `import type { ..., MapLayer } from "../api/types";` if not present.

(c) Append to `shell/src/shell/NewItemButton.test.tsx` (follow its existing render helper):

```ts
test("creates a Map and navigates to the editor route", async () => {
  // See existing tests for the client/router harness; select "Map" then submit.
  // Assert navigation target is /maps/<pk> (createMapItem returns pk).
});
```

Implement this test concretely against the file's existing harness: render `NewItemButton` with a mock client whose `createMapItem` resolves `{ pk: "77", resourceType: "map", ... }`, open the dialog, `selectOptions(Type, "map")`, fill Titre, submit, and assert the router navigated to `/maps/77` (mirror how the existing "create an App" test asserts `/items/<pk>`).

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx src/shell/NewItemButton.test.tsx`
Expected: FAIL — isolation not implemented; NewItemButton has no Map option.

- [ ] **Step 3: Harden `MapView`**

Edit `shell/src/map/MapView.tsx`. Wrap each layer's work in `applyLayers` with try/catch (skip the failing layer, keep going), and change the config-change effect guard to `isStyleLoaded()`:

In `applyLayers`, wrap the body of the `for` loop:

```ts
  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({ id: layer.id, type: "fill", source: layer.id, "source-layer": layer.sourceLayer, paint: layer.paint ?? {} });
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({ id: layer.id, type: "raster", source: layer.id, paint: { "raster-opacity": layer.opacity ?? 1 } });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map.
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
```

In the `[config.layers]` effect, change the guard:

```ts
    if (!map || !map.isStyleLoaded() || !overlay) return;
```

- [ ] **Step 4: Add the "Map" type to `NewItemButton`**

Edit `shell/src/shell/NewItemButton.tsx`:
- Import `useCreateMap`: `import { useCreateItem, useCreateMap } from "../api/hooks";`
- Widen local kind: `const [kind, setKind] = useState<"app" | "dashboard" | "map">("app");`
- `const createMap = useCreateMap();`
- In `close()`, also `createMap.reset();`
- In `submit`, branch on kind:

```ts
    try {
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : await create.mutateAsync({ kind, title: clean, owner: username ?? "" });
      close();
      navigate(kind === "map" ? `/maps/${item.pk}` : `/items/${item.pk}`);
    } catch {
      // error surfaced via isError
    }
```

- Add the option and widen the select cast:

```tsx
              onChange={(e) => setKind(e.target.value as "app" | "dashboard" | "map")}
```
```tsx
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
```

- Update the error condition to cover both mutations:

```tsx
          {(create.isError || createMap.isError) && (
```
and disable the submit while either is pending:
```tsx
            <Button type="submit" size="sm" disabled={create.isPending || createMap.isPending}>
```

- [ ] **Step 5: Route map items to the editor**

Edit `shell/src/ui/ItemCard.tsx` — pass the type up:
```tsx
  onOpen: (pk: string, type: ResourceType) => void;
```
```tsx
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk, item.resourceType)}>
```
(add `import type { ResourceType } from "../api/types";` if `ResourceType` isn't already imported.)

Edit `shell/src/pages/CatalogPage.tsx` — widen the prop and pass through:
```tsx
export function CatalogPage({ onOpenItem }: { onOpenItem: (pk: string, type: ResourceType) => void }) {
```
```tsx
              onOpen={onOpenItem}
```
(add `ResourceType` to the existing `../api/types` import.)

Edit `shell/src/shell/routes.tsx`:
```tsx
import { MapEditorPage } from "../pages/MapEditorPage";
```
```tsx
function CatalogRoute() {
  const navigate = useNavigate();
  return (
    <CatalogPage
      onOpenItem={(pk, type) => navigate(type === "map" ? `/maps/${pk}` : `/items/${pk}`)}
    />
  );
}

function MapEditorRoute() {
  const { pk } = useParams();
  return <MapEditorPage pk={pk!} />;
}
```
and add the route inside `<Routes>`:
```tsx
      <Route path="/maps/:pk" element={<MapEditorRoute />} />
```

Edit `shell/src/pages/ItemDetailPage.tsx` — enable the editor button for maps. Add an optional prop and use it:
```tsx
export function ItemDetailPage({ pk, onDeleted, onOpenEditor }: { pk: string; onDeleted?: () => void; onOpenEditor?: () => void }) {
```
Replace the disabled button with:
```tsx
      {item.resourceType === "map" ? (
        <Button className="w-fit" onClick={onOpenEditor}>Ouvrir dans l'éditeur</Button>
      ) : (
        <Button className="w-fit" disabled title="Disponible avec l'éditeur (SP-0d)">
          Ouvrir dans l'éditeur
        </Button>
      )}
```
And in `routes.tsx` `ItemDetailRoute`, pass the navigate:
```tsx
  return <ItemDetailPage pk={pk!} onDeleted={() => navigate("/")} onOpenEditor={() => navigate(`/maps/${pk}`)} />;
```

- [ ] **Step 6: Run the targeted + full suite**

Run: `cd shell && npx vitest run`
Expected: PASS — including updated catalog/detail/NewItemButton tests. If a catalog or detail test called `onOpen`/`onOpenItem` with one arg, update those call sites/assertions to the new two-arg signature (type defaults are explicit now).

- [ ] **Step 7: Build, then commit**

Run: `cd shell && npm run build`
Expected: build succeeds.

```bash
git add shell/src/shell/routes.tsx shell/src/pages/CatalogPage.tsx shell/src/ui/ItemCard.tsx shell/src/pages/ItemDetailPage.tsx shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/test/MockMaplibreMap.ts
git commit -m "feat(shell): wire map editor route + Map type; harden MapView layer isolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Playwright E2E — create → add layer → save (real render)

**Files:**
- Modify: `shell/e2e/mocks.ts` (add builder + martin/featureserv routes for the map flow)
- Create: `shell/e2e/map-editor.spec.ts`

**Interfaces:**
- Consumes: existing `mockGeoNode(page)` harness + `.env.e2e` (`VITE_MARTIN_URL`/`VITE_FEATURESERV_URL` must be set to routable test hosts the mocks intercept).
- Produces: an E2E that creates a Map, opens the editor, adds a layer from the picker, saves, and asserts the real MapLibre canvas mounted.

- [ ] **Step 1: Extend the E2E mocks**

Edit `shell/e2e/mocks.ts`. Add route handlers (using Playwright `page.route`) for the builder and layer services the map flow hits. Mirror the file's existing style. Cover:
- `POST **/configs` → `{ id: "cfg-1", kind: "map", itemId: "77" }` (201)
- `GET **/configs/by-item/77` → a map `ConfigRead` shaped `{ id:"cfg-1", itemId:"77", kind:"map", config: { kind:"map", map: { basemap, view (France), layers: [] } } }` (the map payload MUST be under `config.map`)
- `PUT **/configs/by-item/77` → echo `{ id:"cfg-1", itemId:"77", kind:"map", map: <body.map> }`
- `GET **/catalog` → `{ tiles: { communes: { description: "Communes" } } }`
- `GET **/collections.json` → `{ collections: [] }`

Ensure the `.env.e2e` used by the Playwright webserver defines `VITE_MARTIN_URL` and `VITE_FEATURESERV_URL` (add them if missing) so `listLayerSources` targets the mocked hosts.

- [ ] **Step 2: Write the E2E**

Create `shell/e2e/map-editor.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("create a Map → add a layer → save → canvas mounts", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Type").selectOption("map");
  await page.getByLabel("Titre").fill("Ma carte");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/maps\/77$/);

  // The real MapLibre canvas mounts (Chromium has WebGL).
  await expect(page.locator("canvas")).toBeVisible();

  // Add a layer from the picker, then save.
  await page.getByRole("button", { name: /Communes/ }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // No error alert after saving.
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);
});
```

- [ ] **Step 3: Run the E2E**

Run: `cd shell && npx playwright test map-editor` (install browsers first if needed: `npx playwright install chromium`)
Expected: PASS — URL is `/maps/77`, a `<canvas>` is visible, save shows no error.

- [ ] **Step 4: Run the full E2E suite to check for regressions**

Run: `cd shell && npx playwright test`
Expected: all specs pass (existing catalog specs + the new map-editor spec).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/map-editor.spec.ts shell/.env.e2e
git commit -m "test(shell): E2E map editor create→add→save with real MapLibre canvas

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (§4, §5, §6, §7, §9, §10 0c-e; §12 deferrals):** `createMapItem`/`getMapConfig`/`saveMapConfig` (§4) → Task 2; builder PUT-by-item the save needs → Task 1. Hooks (§6) → Task 3. `BasemapSelect`/`LayersPanel` (§5) → Task 4; `MapEditorPage` (§5, §7) → Task 5. `NewItemButton` Map type + `/maps/:pk` + open-from-catalog (§5) → Task 6. E2E real render create→add→save (§9) → Task 7. Deferred items now due (§12 notes): per-layer isolation try/catch + `isStyleLoaded()` guard → Task 6; `CreateKind`/"map" creation path → Task 2 (`createMapItem`) + Task 6 (NewItemButton). Save-error `role="alert"` (§8) → Task 5.
- **Placeholder scan:** Task 6 Step 1(c) NewItemButton test and Task 7 mocks are described against existing harnesses rather than fully transcribed because they depend on file-local helpers the implementer must read; every other step carries complete code. The implementer is instructed to mirror the named existing test/mocks. No "TBD"/"handle errors" placeholders.
- **Type consistency:** `MapConfig`/`MapLayer` shapes match `types.ts` and the builder schema; `createMapItem({title,owner})`/`getMapConfig(pk)`/`saveMapConfig(pk,config)` signatures identical across interface, impl, hooks, tests, and MapEditorPage; `onOpen`/`onOpenItem` widened consistently to `(pk, type)` across ItemCard/CatalogPage/routes; `useSaveMap`/`useMapConfig`/`useCreateMap` names stable; basemap style URLs centralised in `basemaps.ts`.
- **Ordering:** backend (T1) → client (T2) → hooks (T3) → widgets (T4) → page (T5) → integration+hardening (T6) → E2E (T7). Each task independently testable.
