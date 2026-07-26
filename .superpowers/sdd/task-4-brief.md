## Task 4: `ExplorerDrawer` — the drill panel (table + map)

**Files:**
- Create: `shell/src/builder/ExplorerDrawer.tsx`
- Test: `shell/src/builder/ExplorerDrawer.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `useExplorerTarget()`, `useCloseExplorer()` from `./ExplorerContext`.
- Consumes (existing code): `useAnalyticsContext()` from `./AnalyticsContext`; `derivePatch(source, ctx, datasets)` from `../lib/analyticsPatch`; `useItemClient()` from `../api/ItemClientProvider`; `MapView`/`MapViewHandle` from `../map/MapView`; types `DataRecord`, `DataSource`, `MapConfig` from `../api/types`.
- Produces (consumed by Task 5): `function ExplorerDrawer(): ReactNode` — a self-contained component with no props, reads everything from context. Renders `null` when `useExplorerTarget()` is `null`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/ExplorerDrawer.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useImperativeHandle } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ExplorerDrawer } from "./ExplorerDrawer";
import { ExplorerProvider, useOpenExplorer } from "./ExplorerContext";
import { AnalyticsContextProvider, useSetCrossFilter } from "./AnalyticsContext";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { DatasetConfig, DataRecord, ItemClient } from "../api/types";

const highlightSpy = vi.fn();

vi.mock("../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config }: { config: { layers: { url?: string }[] } },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: vi.fn(), highlight: highlightSpy }));
      return <div data-testid="mapview" data-url={config.layers[0]?.url ?? ""} />;
    },
  ),
}));

function Opener({ datasetId, dataSourceId }: { datasetId: string; dataSourceId: string }) {
  const open = useOpenExplorer();
  return <button onClick={() => open({ datasetId, dataSourceId })}>open</button>;
}

function CrossFilterSetter() {
  const setCrossFilter = useSetCrossFilter();
  // originSourceId "src1" matches the dataSourceId used by <Opener> below on
  // purpose — proves the drawer stays filtered even "from" its own origin,
  // since its synthetic query source id is always "__explorer__", never a
  // real widget id (design §4).
  return <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>;
}

function renderDrawer(opts: { queryDataSource?: ReturnType<typeof vi.fn> } = {}) {
  const dataset: DatasetConfig = { source: "collection", collectionId: "col-1", columns: { nom: { label: "Nom" } } };
  const getDatasetConfig = vi.fn().mockResolvedValue(dataset);
  const queryDataSource = opts.queryDataSource ?? vi.fn().mockResolvedValue([]);
  const featuresUrl = vi.fn().mockReturnValue("https://core.test/collections/col-1/items?region=Nord");
  const client = { getDatasetConfig, queryDataSource, featuresUrl } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <ExplorerProvider enabled>
            <Opener datasetId="ds1" dataSourceId="src1" />
            <CrossFilterSetter />
            <ExplorerDrawer />
          </ExplorerProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { queryDataSource, featuresUrl };
}

beforeEach(() => { highlightSpy.mockClear(); });

test("renders nothing when no target is open", () => {
  renderDrawer();
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("opening a target queries the raw dataset features with the analytics context applied, even from its own origin widget", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
  ]);
  renderDrawer({ queryDataSource });
  await userEvent.click(screen.getByText("set-cf"));
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc A");
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    id: "__explorer__",
    datasetId: "ds1",
    query: expect.objectContaining({ limit: 200, region: "Nord" }),
  }));
});

test("table column headers use the dataset's business labels when available", async () => {
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "Parc A" } }]) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText("Nom")).toBeInTheDocument();
});

test("shows the 200-row cap message when the limit is reached", async () => {
  const records: DataRecord[] = Array.from({ length: 200 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText(/200 premières affichées/)).toBeInTheDocument();
});

test("paginates 20 rows at a time", async () => {
  const records: DataRecord[] = Array.from({ length: 25 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc 0");
  expect(screen.queryByText("Parc 20")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(await screen.findByText("Parc 20")).toBeInTheDocument();
  expect(screen.queryByText("Parc 0")).not.toBeInTheDocument();
});

test("clicking a row highlights it on the drawer's own map without touching the analytics context", async () => {
  const record = { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } };
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([record]) });
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByText("Parc A"));
  expect(highlightSpy).toHaveBeenCalledWith(record.geometry);
});

test("closing via the close button clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByRole("button", { name: "Fermer le panneau" }));
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("closing via Escape clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await screen.findByRole("button", { name: "Fermer le panneau" });
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerDrawer"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/ExplorerDrawer.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCloseExplorer, useExplorerTarget } from "./ExplorerContext";
import { useAnalyticsContext } from "./AnalyticsContext";
import { useItemClient } from "../api/ItemClientProvider";
import { derivePatch } from "../lib/analyticsPatch";
import type { DataRecord, DataSource, MapConfig } from "../api/types";
import type { MapViewHandle } from "../map/MapView";

const MapView = lazy(() => import("../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";
const EXPLORER_LIMIT = 200;
const PAGE_SIZE = 20;

function columnsOf(records: DataRecord[]): string[] {
  return records[0] ? Object.keys(records[0].properties) : [];
}

export function ExplorerDrawer() {
  const target = useExplorerTarget();
  const close = useCloseExplorer();
  const analyticsCtx = useAnalyticsContext();
  const client = useItemClient();
  const mapHandle = useRef<MapViewHandle>(null);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  useEffect(() => {
    setPage(0);
    setSelectedId(null);
  }, [target?.datasetId]);

  useEffect(() => {
    if (!target) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [target, close]);

  const datasetQuery = useQuery({
    queryKey: ["dataset", target?.datasetId],
    queryFn: () => client.getDatasetConfig(target!.datasetId),
    enabled: Boolean(target),
  });
  const dataset = datasetQuery.data;

  const source: DataSource | null = target
    ? { id: "__explorer__", type: "features", service: "core", layer: "", datasetId: target.datasetId, query: { limit: EXPLORER_LIMIT } }
    : null;
  const patch = source && dataset ? derivePatch(source, analyticsCtx, { [target!.datasetId]: dataset }) : {};
  const merged: DataSource | null = source ? { ...source, query: { ...source.query, ...patch } } : null;

  const recordsQuery = useQuery({
    queryKey: ["datasource-explorer", target?.datasetId, merged?.query],
    queryFn: () => client.queryDataSource(merged!),
    enabled: Boolean(merged && dataset),
  });

  if (!target) return null;

  const records = recordsQuery.data ?? [];
  const columns = columnsOf(records);
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const shown = records.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  const mapConfig: MapConfig = {
    basemap: { style: DEFAULT_STYLE },
    view: { center: [2.4, 46.6], zoom: 5 },
    layers: merged ? [{ id: "explorer", title: "Entités", visible: true, kind: "feature", url: client.featuresUrl(merged) }] : [],
  };

  function selectRecord(r: DataRecord) {
    setSelectedId(r.id);
    mapHandle.current?.highlight(r.geometry ?? null);
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-lg">
      <div className="flex items-center justify-between border-b border-[var(--gs-color-border)] p-2">
        <h2 className="text-sm font-medium text-[var(--gs-color-text)]">
          Entités — {dataset?.collectionId ?? target.datasetId}
        </h2>
        <button type="button" aria-label="Fermer le panneau" className="text-lg text-[var(--gs-color-muted)]" onClick={close}>
          ×
        </button>
      </div>
      <div className="h-48 shrink-0">
        <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
          <MapView ref={mapHandle} config={mapConfig} />
        </Suspense>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto p-2 text-xs">
        {recordsQuery.isLoading && <p className="text-[var(--gs-color-muted)]">Chargement…</p>}
        {recordsQuery.isError && <p className="text-red-600">Erreur de données</p>}
        {!recordsQuery.isLoading && !recordsQuery.isError && records.length === 0 && (
          <p className="text-[var(--gs-color-muted)]">Aucune entité</p>
        )}
        {records.length >= EXPLORER_LIMIT && (
          <p className="mb-2 text-[var(--gs-color-muted)]">
            Affinez le contexte (période, emprise, filtre) pour voir l'ensemble des entités — {EXPLORER_LIMIT} premières affichées.
          </p>
        )}
        {shown.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b border-[var(--gs-color-border)] p-1 font-medium">
                    {dataset?.columns[c]?.label ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className={`cursor-pointer hover:bg-[var(--gs-color-surface)] ${selectedId === r.id ? "bg-[var(--gs-color-surface)]" : ""}`}
                  onClick={() => selectRecord(r)}
                >
                  {columns.map((c) => (
                    <td key={c} className="border-b border-[var(--gs-color-border)] p-1">
                      {String(r.properties[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pageCount > 1 && (
          <div className="mt-auto flex items-center justify-between pt-2 text-[10px] text-[var(--gs-color-muted)]">
            <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
            <span>Page {current + 1} / {pageCount}</span>
            <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx`
Expected: PASS (8/8).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/ExplorerDrawer.tsx shell/src/builder/ExplorerDrawer.test.tsx
git commit -m "feat(shell): ExplorerDrawer — table+map drill panel for the active analytics context (SP-14d)"
```

---

