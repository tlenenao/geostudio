# GeoStudio SP-0d.2 — Sources de données & widgets liés — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let builder apps bind widgets to platform data — define data sources (pg_featureserv features + static), resolve them via the item-client, feed them into the renderer, and ship four data-bound widgets (Liste, Table, Indicateur, Carte).

**Architecture:** A `DataSource` describes a features/static source; the item-client `queryDataSource` resolves it to `DataRecord[]` (façade-only, no URL leakage). `AppRenderer` wraps its canvas in a `DataProvider` that resolves all `config.dataSources` at once via TanStack `useQueries` and exposes an id→`DataSourceState` map; `WidgetHost` passes the bound state (`props.dataSourceId`) to each widget via `ctx.data`. A `DataSourcePanel` manages sources; each data-bound widget's PropsPanel gets the app's `dataSources` to pick one. The Carte widget reuses SP-0c's `MapView` with a feature layer built from the source's items URL. Server-side statistics are deferred to SP-0d.4 — the Indicateur aggregates records client-side.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + MSW + Playwright; TanStack Query v5 (`useQueries`); reuses `MapView` (mocked in unit).

## Global Constraints

- Front: ALL network via `item-client`; no service URL hard-coded — feature URLs come only from the façade (`featuresUrl`/`queryDataSource`), never from a widget.
- One rendering engine (`AppRenderer`) for edit/preview/runtime — data resolves in all modes.
- `Item`/`ItemClient`/`AppConfig`/`WidgetDefinition` extended by ADDITION; existing tests stay green; `npm run build` passes.
- A widget in error (incl. a failed data source) must never break the whole app (`WidgetHost` isolation + per-widget loading/error states).
- Heavy libs (MapLibre/Deck via MapView) mocked in unit; real render only in E2E.
- No token in localStorage. MSW `onUnhandledRequest:"error"`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`.
- `createItemClient` already receives `featureservUrl` (SP-0c-d). Backend `DataSource` schema (`id,type,service,layer,query`) already exists and round-trips inside `BuilderConfig.dataSources`.

---

### Task 1: Data-source types + item-client `queryDataSource`/`featuresUrl`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces:
  - `DataSource = { id: string; type: "features" | "static"; service: string; layer: string; query: Record<string, unknown> }`
  - `DataRecord = { id: string | number; properties: Record<string, unknown>; geometry?: unknown }`
  - `DataSourceState = { loading: boolean; error: boolean; records: DataRecord[]; url?: string }`
  - `AppConfig.dataSources: DataSource[]` (was `unknown[]`)
  - `WidgetContext.data?: DataSourceState`
  - `ItemClient.queryDataSource(source: DataSource): Promise<DataRecord[]>` and `ItemClient.featuresUrl(source: DataSource): string`

- [ ] **Step 1: Add the data types**

Edit `shell/src/api/types.ts`. Add near `AppConfig`:

```ts
export type DataSource = {
  id: string;
  type: "features" | "static";
  service: string;
  layer: string;
  query: Record<string, unknown>;
};

export type DataRecord = {
  id: string | number;
  properties: Record<string, unknown>;
  geometry?: unknown;
};

export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  url?: string;
};
```

Change `AppConfig.dataSources` from `unknown[]` to `DataSource[]`. Add to the `ItemClient` interface (after `saveAppConfig`):

```ts
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
```

- [ ] **Step 2: Write the failing MSW tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("featuresUrl builds the featureserv items url", () => {
  const url = makeClient().featuresUrl({ id: "d", type: "features", service: "featureserv", layer: "public.parcs", query: {} });
  expect(url).toBe("https://featureserv.test/collections/public.parcs/items.json");
});

test("queryDataSource maps a feature collection to records", async () => {
  server.use(
    http.get("https://featureserv.test/collections/public.parcs/items.json", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { type: "Feature", id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
          { type: "Feature", properties: { nom: "Parc B" }, geometry: null },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({ id: "d", type: "features", service: "featureserv", layer: "public.parcs", query: {} });
  expect(records).toHaveLength(2);
  expect(records[0]).toMatchObject({ id: 1, properties: { nom: "Parc A" } });
  // Missing feature id falls back to the index.
  expect(records[1].id).toBe(1);
});

test("queryDataSource returns inline records for a static source", async () => {
  const records = await makeClient().queryDataSource({
    id: "s", type: "static", service: "", layer: "",
    query: { records: [{ id: "a", properties: { v: 1 } }] },
  });
  expect(records).toEqual([{ id: "a", properties: { v: 1 } }]);
});

test("queryDataSource throws when the feature request fails", async () => {
  server.use(
    http.get("https://featureserv.test/collections/x/items.json", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(
    makeClient().queryDataSource({ id: "d", type: "features", service: "featureserv", layer: "x", query: {} }),
  ).rejects.toThrow();
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — methods not implemented.

- [ ] **Step 4: Implement the two methods**

Edit `shell/src/api/itemClient.ts`. Add `DataSource`/`DataRecord` to the type import. Add both methods to the returned client object (after `saveAppConfig`):

```ts
    featuresUrl(source: DataSource): string {
      return `${featureservUrl}/collections/${source.layer}/items.json`;
    },

    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      if (source.type === "static") {
        return (source.query.records as DataRecord[] | undefined) ?? [];
      }
      const token = getToken();
      const res = await fetch(this.featuresUrl(source), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${source.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      return (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
    },
```

NOTE: `this.featuresUrl` requires the returned object to be referenced as `this`. Because the object literal is returned directly, `this` inside `queryDataSource` is that object at call time. If the existing file's methods are arrow-free object methods (they are `async name()` shorthand), `this` binds correctly. If any test calls `queryDataSource` detached, it would break — but tests call it on the client instance, so `this` is valid. (Alternatively, hoist `featuresUrl` to a local `const featuresUrl = (source) => ...` above the return and call that; if you prefer that, expose it on the object too. Pick one and keep it consistent.)

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 6: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add DataSource types + queryDataSource/featuresUrl

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `DataProvider` + wire data into `AppRenderer`/`WidgetHost`

**Files:**
- Create: `shell/src/builder/DataContext.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx`, `shell/src/builder/WidgetHost.tsx`
- Test: `shell/src/builder/DataContext.test.tsx`

**Interfaces:**
- Consumes: `useItemClient`, `queryDataSource`/`featuresUrl`, `DataSource`/`DataSourceState`, `useQueries`.
- Produces:
  - `DataProvider({ sources, children })` — resolves all sources via `useQueries`, provides an id→`DataSourceState` map.
  - `useDataStates(): Record<string, DataSourceState>`.
  - `AppRenderer` wraps its canvas in `DataProvider sources={config.dataSources}`.
  - `WidgetHost` reads `useDataStates()` and passes `ctx.data = states[item.props.dataSourceId]`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/DataContext.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { DataSource, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DataProvider, useDataStates } from "./DataContext";

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} },
];

function Probe() {
  const states = useDataStates();
  const s = states["ds1"];
  if (!s || s.loading) return <p>loading</p>;
  return <p>records:{s.records.length} url:{s.url}</p>;
}

test("resolves sources and exposes their state", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: {} }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={sources}>
          <Probe />
        </DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText(/records:1/)).toBeInTheDocument());
  expect(screen.getByText(/url:https:\/\/fs\/parcs\/items.json/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `DataContext`**

Create `shell/src/builder/DataContext.tsx`:

```tsx
import { createContext, useContext, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { DataSource, DataSourceState } from "../api/types";

const DataStatesContext = createContext<Record<string, DataSourceState>>({});

export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
  const results = useQueries({
    queries: sources.map((s) => ({
      queryKey: ["datasource", s.id, s.query],
      queryFn: () => client.queryDataSource(s),
    })),
  });
  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      url: s.type === "features" ? client.featuresUrl(s) : undefined,
    };
  });
  return <DataStatesContext.Provider value={states}>{children}</DataStatesContext.Provider>;
}

export function useDataStates(): Record<string, DataSourceState> {
  return useContext(DataStatesContext);
}
```

- [ ] **Step 4: Wire `DataProvider` into `AppRenderer`**

Edit `shell/src/builder/AppRenderer.tsx` — wrap the `GridCanvas` in `DataProvider`:

```tsx
import { DataProvider } from "./DataContext";
```

Wrap the returned `GridCanvas`:

```tsx
  return (
    <DataProvider sources={config.dataSources}>
      <GridCanvas
        items={config.layout.items}
        editable={editable}
        selectedId={selectedId}
        onSelect={(id) => onSelect?.(id)}
        onMoveItem={handleMove}
        renderItem={(item) => <WidgetHost item={item} mode={mode} />}
      />
    </DataProvider>
  );
```

- [ ] **Step 5: Pass bound data through `WidgetHost`**

Edit `shell/src/builder/WidgetHost.tsx` — read the states and pass `ctx.data`:

```tsx
import { useDataStates } from "./DataContext";
```

Inside `WidgetHost`, before rendering the widget:

```tsx
  const states = useDataStates();
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
```

and render `<Widget props={item.props} ctx={{ mode, data }} />`.

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (Existing WidgetHost/AppRenderer tests must render within a `QueryClientProvider`; if any now fail because `DataProvider` needs a QueryClient, wrap those tests' renders in a `QueryClientProvider` — the `DataProvider` calls `useQueries`. Update those existing tests minimally.)

```bash
git add shell/src/builder/DataContext.tsx shell/src/builder/DataContext.test.tsx shell/src/builder/AppRenderer.tsx shell/src/builder/WidgetHost.tsx shell/src/builder/AppRenderer.test.tsx shell/src/builder/WidgetHost.test.tsx
git commit -m "feat(shell): resolve data sources in AppRenderer and pass to widgets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Extend widget PropsPanel with data sources + `DataSourceSelect`

**Files:**
- Modify: `shell/src/builder/registry.ts` (PropsPanel signature)
- Modify: `shell/src/builder/PropsPanel.tsx` (pass `dataSources`)
- Create: `shell/src/builder/DataSourceSelect.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx` (pass `draft.dataSources` to PropsPanel)
- Test: `shell/src/builder/DataSourceSelect.test.tsx`, `shell/src/builder/PropsPanel.test.tsx` (extend)

**Interfaces:**
- Produces:
  - `WidgetDefinition.PropsPanel: (p: { props; onChange; dataSources: DataSource[] }) => ReactNode`
  - `PropsPanel({ item, dataSources, onChange })` passes `dataSources` down.
  - `DataSourceSelect({ value, dataSources, onChange })` — a `<select>` (with an empty "Aucune" option) binding `props.dataSourceId`.

- [ ] **Step 1: Extend the PropsPanel signature (additive arg)**

Edit `shell/src/builder/registry.ts` — widen the `PropsPanel` type:

```ts
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
```

Add `import type { DataSource } from "../api/types";`. The three builtin widgets (text/image/button) ignore the new arg — no change needed to them (extra prop is allowed), but their `PropsPanel` type now includes `dataSources`; TS is structurally fine since they don't use it.

- [ ] **Step 2: Write the failing DataSourceSelect test**

Create `shell/src/builder/DataSourceSelect.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource } from "../api/types";
import { DataSourceSelect } from "./DataSourceSelect";

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "fs", layer: "parcs", query: {} },
  { id: "ds2", type: "static", service: "", layer: "", query: {} },
];

test("selects a data source and emits its id", async () => {
  const onChange = vi.fn();
  render(<DataSourceSelect value="" dataSources={sources} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds2");
  expect(onChange).toHaveBeenCalledWith("ds2");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataSourceSelect.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement `DataSourceSelect`**

Create `shell/src/builder/DataSourceSelect.tsx`:

```tsx
import type { DataSource } from "../api/types";

export function DataSourceSelect({
  value,
  dataSources,
  onChange,
}: {
  value: string;
  dataSources: DataSource[];
  onChange: (id: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      Source de données
      <select
        aria-label="Source de données"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Aucune</option>
        {dataSources.map((s) => (
          <option key={s.id} value={s.id}>{s.layer || s.id}</option>
        ))}
      </select>
    </label>
  );
}
```

- [ ] **Step 5: Thread `dataSources` through `PropsPanel`**

Edit `shell/src/builder/PropsPanel.tsx`:

```tsx
import type { DataSource, WidgetItem } from "../api/types";

export function PropsPanel({
  item,
  dataSources,
  onChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  onChange: (props: Record<string, unknown>) => void;
}) {
  if (!item) return <p className="text-xs text-slate-400">Aucun widget sélectionné.</p>;
  const def = getWidget(item.widget);
  if (!def) return <p className="text-xs text-slate-400">Widget inconnu : {item.widget}</p>;
  const Panel = def.PropsPanel;
  return <Panel props={item.props} dataSources={dataSources} onChange={(p) => onChange(p)} />;
}
```

Update `shell/src/builder/PropsPanel.test.tsx`: pass `dataSources={[]}` to each `<PropsPanel .../>` render.

Edit `shell/src/pages/AppBuilderPage.tsx` — pass the draft's sources:

```tsx
            <PropsPanel item={selected} dataSources={draft.dataSources} onChange={updateSelectedProps} />
```

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/DataSourceSelect.test.tsx src/builder/PropsPanel.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/registry.ts shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx shell/src/builder/DataSourceSelect.tsx shell/src/builder/DataSourceSelect.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "feat(shell): thread data sources into widget PropsPanels + DataSourceSelect

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Liste & Table widgets (data-bound)

**Files:**
- Create: `shell/src/builder/widgets/data.tsx`
- Modify: `shell/src/builder/widgets/index.tsx` (register the two)
- Test: `shell/src/builder/widgets/data.test.tsx`

**Interfaces:**
- Consumes: `registerWidget`, `WidgetContext.data`, `DataSourceSelect`, `DataRecord`.
- Produces: `registerDataWidgets()` registering `list` and `table`; called from `registerBuiltinWidgets()`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/widgets/data.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState =>
  ({ loading: false, error: false, records: [], ...over });

test("list renders a record per row using the title field", () => {
  const List = getWidget("list")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "Parc A" } }, { id: 2, properties: { nom: "Parc B" } },
  ] }) } as WidgetContext;
  render(<List props={{ dataSourceId: "d", titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toBeInTheDocument();
  expect(screen.getByText("Parc B")).toBeInTheDocument();
});

test("list shows loading and empty states", () => {
  const List = getWidget("list")!.Component;
  const { rerender } = render(<List props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<List props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("table renders headers from columns and a cell per column", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "A", ville: "X" } },
  ] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom", "ville"] }} ctx={ctx} />);
  expect(screen.getByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "X" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: FAIL — `list`/`table` not registered.

- [ ] **Step 3: Implement the data widgets**

Create `shell/src/builder/widgets/data.tsx`:

```tsx
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import type { DataRecord } from "../../api/types";

function firstField(records: DataRecord[]): string | undefined {
  return records[0] ? Object.keys(records[0].properties)[0] : undefined;
}

export function registerDataWidgets(): void {
  registerWidget({
    type: "list",
    label: "Liste",
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Champ titre
          <input aria-label="Champ titre" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.titleField ?? "")} onChange={(e) => onChange({ ...props, titleField: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
      const field = String(props.titleField || firstField(data.records) || "");
      return (
        <ul className="flex flex-col gap-0.5 text-sm">
          {data.records.map((r) => (
            <li key={String(r.id)} className="truncate border-b border-slate-100 py-0.5">
              {String(r.properties[field] ?? r.id)}
            </li>
          ))}
        </ul>
      );
    },
  });

  registerWidget({
    type: "table",
    label: "Table",
    defaultProps: { dataSourceId: "", columns: [] },
    defaultSize: { w: 6, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Colonnes (séparées par des virgules)
          <input aria-label="Colonnes" className="h-9 rounded-md border border-slate-300 px-2"
            value={(props.columns as string[] | undefined)?.join(",") ?? ""}
            onChange={(e) => onChange({ ...props, columns: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const columns = ((props.columns as string[] | undefined)?.length
        ? (props.columns as string[])
        : Object.keys(data.records[0]?.properties ?? {}));
      return (
        <table className="w-full text-left text-xs">
          <thead>
            <tr>{columns.map((c) => <th key={c} className="border-b p-1">{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.records.map((r) => (
              <tr key={String(r.id)}>
                {columns.map((c) => <td key={c} className="border-b border-slate-100 p-1">{String(r.properties[c] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      );
    },
  });
}
```

- [ ] **Step 4: Register the data widgets**

Edit `shell/src/builder/widgets/index.tsx` — import and call `registerDataWidgets()` inside `registerBuiltinWidgets()` (after the three builtins, before the guard returns nothing further):

```tsx
import { registerDataWidgets } from "./data";
```
At the end of `registerBuiltinWidgets()` (still inside, after the button registration):
```tsx
  registerDataWidgets();
```

- [ ] **Step 5: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/widgets/data.tsx shell/src/builder/widgets/data.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add data-bound Liste and Table widgets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Indicateur & Carte widgets

**Files:**
- Create: `shell/src/builder/widgets/indicator.tsx`, `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/index.tsx` (register both)
- Test: `shell/src/builder/widgets/indicator.test.tsx`, `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `registerWidget`, `WidgetContext.data`, `DataSourceSelect`, `MapView`, `MapConfig`.
- Produces: `registerIndicatorWidget()` (`indicator`) and `registerMapWidget()` (`map`), both called from `registerBuiltinWidgets()`.

- [ ] **Step 1: Write the failing Indicateur test**

Create `shell/src/builder/widgets/indicator.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

test("indicator counts records by default", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } },
  ] }) } as WidgetContext;
  render(<Ind props={{ dataSourceId: "d", label: "Total", agg: "count" }} ctx={ctx} />);
  expect(screen.getByText("Total")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});

test("indicator sums a field when agg=sum", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } },
  ] }) } as WidgetContext;
  render(<Ind props={{ dataSourceId: "d", agg: "sum", field: "pop" }} ctx={ctx} />);
  expect(screen.getByText("40")).toBeInTheDocument();
});
```

Create `shell/src/builder/widgets/mapWidget.test.tsx` (the widget lazy-loads `MapView`; `vi.mock` intercepts the dynamic import, and the tests `await` the lazy resolution):

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";

vi.mock("../../map/MapView", () => ({
  MapView: ({ config }: { config: { layers: { url?: string }[] } }) => (
    <div data-testid="mapview">layers:{config.layers.length} url:{config.layers[0]?.url ?? ""}</div>
  ),
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(<Map props={{ dataSourceId: "d" }} ctx={ctx} />);
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:1");
  expect(view).toHaveTextContent("url:https://fs/parcs/items.json");
});

test("map widget renders an empty map when no source is bound", async () => {
  const Map = getWidget("map")!.Component;
  render(<Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />);
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:0");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL — `indicator`/`map` not registered.

- [ ] **Step 3: Implement the Indicateur widget**

Create `shell/src/builder/widgets/indicator.tsx`:

```tsx
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";

export function registerIndicatorWidget(): void {
  registerWidget({
    type: "indicator",
    label: "Indicateur",
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé de l'indicateur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Agrégation
          <select aria-label="Agrégation" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.agg ?? "count")} onChange={(e) => onChange({ ...props, agg: e.target.value })}>
            <option value="count">Nombre</option>
            <option value="sum">Somme</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">Champ (pour la somme)
          <input aria-label="Champ agrégé" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;
      const agg = String(props.agg ?? "count");
      const field = String(props.field ?? "");
      const value =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      return (
        <div className="flex h-full flex-col items-center justify-center">
          <span className="text-2xl font-semibold">{value}</span>
          <span className="text-xs text-slate-500">{String(props.label ?? "")}</span>
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Implement the Carte widget**

Create `shell/src/builder/widgets/mapWidget.tsx`. `MapView` (which imports `maplibre-gl`) is **lazy-loaded** so merely importing this module — as `registerBuiltinWidgets` does — never pulls `maplibre-gl` into the module graph; it loads only when the Carte widget actually renders:

```tsx
import { lazy, Suspense } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import type { MapConfig } from "../../api/types";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id })} />
    ),
    Component: ({ props, ctx }) => {
      const url = ctx.data?.url;
      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url }]
          : [],
      };
      return (
        <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
          <MapView config={config} />
        </Suspense>
      );
    },
  });
}
```

- [ ] **Step 5: Register both**

Edit `shell/src/builder/widgets/index.tsx` — import and call inside `registerBuiltinWidgets()`:

```tsx
import { registerIndicatorWidget } from "./indicator";
import { registerMapWidget } from "./mapWidget";
```
At the end of `registerBuiltinWidgets()`:
```tsx
  registerIndicatorWidget();
  registerMapWidget();
```

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx src/builder/widgets/mapWidget.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. Because `mapWidget.tsx` lazy-loads `MapView`, importing `registerBuiltinWidgets` in other suites does NOT pull `maplibre-gl` into the module graph — only rendering the Carte widget triggers the dynamic import (and only `mapWidget.test.tsx` does that, with `MapView` mocked). Confirm no existing builder test breaks in the full-suite run.

```bash
git add shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add Indicateur and Carte (MapView-backed) widgets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `DataSourcePanel` + integrate into `AppBuilderPage`

**Files:**
- Create: `shell/src/builder/DataSourcePanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/DataSourcePanel.test.tsx`, `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Produces:
  - `DataSourcePanel({ sources, onChange })` — add a source (id via `crypto.randomUUID()`, type features/static, editable layer), remove a source; `onChange(nextSources)`.
  - `AppBuilderPage` renders `DataSourcePanel` in the left rail and persists `draft.dataSources`.

- [ ] **Step 1: Write the failing DataSourcePanel test**

Create `shell/src/builder/DataSourcePanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource } from "../api/types";
import { DataSourcePanel } from "./DataSourcePanel";

test("adds a data source", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  const next = onChange.mock.calls[0][0] as DataSource[];
  expect(next).toHaveLength(1);
  expect(next[0].type).toBe("features");
  expect(typeof next[0].id).toBe("string");
});

test("removes a data source", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "features", service: "featureserv", layer: "parcs", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer parcs" }));
  expect(onChange).toHaveBeenCalledWith([]);
});

test("edits a source layer", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "features", service: "featureserv", layer: "", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Collection de la source d1"), "parcs");
  const last = onChange.mock.calls.at(-1)![0] as DataSource[];
  expect(last[0].layer.endsWith("s")).toBe(true);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `DataSourcePanel`**

Create `shell/src/builder/DataSourcePanel.tsx`:

```tsx
import type { DataSource } from "../api/types";

export function DataSourcePanel({
  sources,
  onChange,
}: {
  sources: DataSource[];
  onChange: (sources: DataSource[]) => void;
}) {
  function add() {
    onChange([
      ...sources,
      { id: crypto.randomUUID(), type: "features", service: "featureserv", layer: "", query: {} },
    ]);
  }
  function remove(id: string) {
    onChange(sources.filter((s) => s.id !== id));
  }
  function patch(id: string, changes: Partial<DataSource>) {
    onChange(sources.map((s) => (s.id === id ? { ...s, ...changes } : s)));
  }
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {sources.map((s) => (
          <li key={s.id} className="rounded border border-slate-200 p-2 text-sm">
            <div className="flex items-center justify-between">
              <select aria-label={`Type de la source ${s.id}`} className="h-8 rounded border border-slate-300 text-xs"
                value={s.type} onChange={(e) => patch(s.id, { type: e.target.value as DataSource["type"] })}>
                <option value="features">Features</option>
                <option value="static">Statique</option>
              </select>
              <button type="button" aria-label={`Retirer ${s.layer || s.id}`} className="text-xs text-red-600" onClick={() => remove(s.id)}>✕</button>
            </div>
            {s.type === "features" && (
              <input aria-label={`Collection de la source ${s.id}`} placeholder="collection"
                className="mt-1 h-8 w-full rounded border border-slate-300 px-2 text-xs"
                value={s.layer} onChange={(e) => patch(s.id, { layer: e.target.value })} />
            )}
          </li>
        ))}
        {sources.length === 0 && <li className="text-xs text-slate-400">Aucune source.</li>}
      </ul>
      <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
        Ajouter une source
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Integrate into `AppBuilderPage`**

Edit `shell/src/pages/AppBuilderPage.tsx`:
- Import `DataSourcePanel`.
- Add a `setSources` helper:
```tsx
  const setSources = (dataSources: typeof draft.dataSources) => setDraft({ ...draft, dataSources });
```
- In the left rail (edit mode), below the widget palette, render:
```tsx
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Sources de données</p>
            <DataSourcePanel sources={draft.dataSources} onChange={setSources} />
```

- [ ] **Step 5: Extend the AppBuilderPage test**

Add to `shell/src/pages/AppBuilderPage.test.tsx` a test that adds a data source and saves, asserting the saved config has one source:

```tsx
test("adds a data source and persists it", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Ajouter une source" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.dataSources).toHaveLength(1);
});
```

(The existing `config` fixture has `dataSources: []`; the render already wraps the page in QueryClient+ItemClientProvider. Since `AppRenderer` now mounts `DataProvider` which calls `useQueries`, the empty `dataSources` array means no queries fire — no extra MSW/mock needed.)

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx src/pages/AppBuilderPage.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): add DataSourcePanel and wire it into the app builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: E2E — bind a data source to a List widget

**Files:**
- Modify: `shell/e2e/mocks.ts`
- Create: `shell/e2e/data-widget.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock (SP-0d.1 Task 8), `.env.e2e` (`VITE_FEATURESERV_URL`).
- Produces: an E2E that creates an App, adds a features source (collection `parcs`), adds a List widget bound to it, saves, opens the runtime, and asserts a record renders.

- [ ] **Step 1: Extend the E2E mocks**

Edit `shell/e2e/mocks.ts`. Add a route for the featureserv items endpoint the List will read:
- `GET **/collections/parcs/items.json` → `{ type:"FeatureCollection", features:[ { id:1, properties:{ nom:"Parc du Test" } }, { id:2, properties:{ nom:"Bois Test" } } ] }`.

(The by-item stateful store from SP-0d.1 already returns the saved app config on the runtime GET, so the saved List widget + its `dataSourceId` and the source definition round-trip.)

- [ ] **Step 2: Write the E2E**

Create `shell/e2e/data-widget.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("bind a features source to a List widget → runtime shows a record", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App données");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a features data source and name its collection.
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");

  // Add a List widget and bind it to the source.
  await page.getByRole("button", { name: "Liste" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ titre").fill("nom");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime shows a record from the bound source.
  await page.goto("/apps/9");
  await expect(page.getByText("Parc du Test")).toBeVisible();
});
```

- [ ] **Step 3: Run the new E2E**

Run: `cd shell && npx playwright test data-widget`
Expected: PASS — runtime shows "Parc du Test".

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/data-widget.spec.ts
git commit -m "test(shell): E2E bind features source to a List widget in the builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (§7 data sources, §5 components, §13 SP-0d.2):** `DataSource` + `queryDataSource` (features + static) → Task 1; data resolution in `AppRenderer` via `useQueries` + widget binding → Task 2; binding UI (PropsPanel dataSources + `DataSourceSelect`) → Task 3; Liste/Table → Task 4; Indicateur (client-side agg) + Carte (reuses `MapView`) → Task 5; `DataSourcePanel` + builder integration → Task 6; E2E bind→save→runtime → Task 7. Server-side statistics source deferred to SP-0d.4 (documented); Indicateur aggregates records client-side.
- **Placeholder scan:** none — every step carries complete code. Task 5's maplibre-import note and Task 6's setSources are described with exact code.
- **Type consistency:** `DataSource`/`DataRecord`/`DataSourceState` identical across types.ts, itemClient, DataContext, widgets, DataSourcePanel; `queryDataSource`/`featuresUrl` signatures match interface/impl/mock; `WidgetContext.data` additive; `PropsPanel` signature widened consistently across registry + PropsPanel + all widget defs (existing text/image/button ignore the new `dataSources` arg — structurally compatible); `AppConfig.dataSources` typed `DataSource[]` used by DataProvider/DataSourcePanel/AppBuilderPage.
- **Façade discipline:** feature URLs only from `featuresUrl`/`queryDataSource` (item-client); the Carte widget gets the URL via `ctx.data.url` (populated in `DataProvider` from the façade), never constructs a service URL itself.
- **Maplibre isolation:** the Carte widget lazy-loads `MapView` (`React.lazy` + `Suspense`), so `registerBuiltinWidgets` never pulls `maplibre-gl` into the module graph of the many suites that register widgets; only `mapWidget.test.tsx` renders it, with `MapView` mocked. No global mock needed.
