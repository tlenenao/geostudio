## Task 3: `map` widget — color/size encodings, domain queries, legend overlay

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `detectGeometryKind`, `buildMapPaint`, `buildLegend`, `MapEncodings`, `ColorDomain`, `SizeDomain`, `LegendSpec` from Task 1 (`./mapSymbology`); `MapLayer.renderAs` from Task 2 (`../../api/types`); `useItemClient` from `../../api/ItemClientProvider` (pre-existing, used the same way by `sliderFilter.tsx`/`selectFilter.tsx`).
- Produces: nothing consumed by later tasks — Task 4's E2E tests exercise this widget only through the real builder UI (palette button `"Carte"`, PropsPanel fields `"Champ couleur"`/`"Type de couleur"`/`"Champ taille"`), not by importing anything from this file.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `shell/src/builder/widgets/mapWidget.test.tsx` with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange, onFeatureClick }: {
        config: { layers: { url?: string; renderAs?: string; paint?: Record<string, unknown> }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void;
        onFeatureClick?: (record: { id: string | number; properties: Record<string, unknown>; geometry?: unknown }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      const layer = config.layers[0];
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}>
          layers:{config.layers.length} url:{layer?.url ?? ""} renderAs:{layer?.renderAs ?? ""} paint:{JSON.stringify(layer?.paint ?? {})}
          <button
            type="button"
            data-testid="feature"
            onClick={() => onFeatureClick?.({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } })}
          >
            feature
          </button>
        </div>
      );
    },
  ),
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); flyToSpy.mockClear(); highlightSpy.mockClear(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

// Every Component test now needs QueryClientProvider + ItemClientProvider —
// the widget calls useItemClient()/useQuery() unconditionally to fetch a
// color/size domain, same as sliderFilter.tsx/selectFilter.tsx already do.
// Pre-existing tests never configure `encodings`, so those two domain
// queries stay `enabled: false` and `queryDataSource` is never actually
// invoked for them — a bare vi.fn() default is safe.
function withClient(children: React.ReactNode, queryDataSource: ReturnType<typeof vi.fn> = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("registers with a 6x6 default size", () => {
  expect(getWidget("map")!.defaultSize).toEqual({ w: 6, h: 6 });
});

test("PropsPanel edits the color and size encodings", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("map")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{}} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  // Single characters only: props never gets fed back between keystrokes in
  // this test (same convention as pivot.test.tsx's PropsPanel test), so each
  // assertion reflects setEncodings() merging against the still-empty base
  // `props={{}}`, not an accumulated string.
  await userEvent.type(screen.getByLabelText("Champ couleur"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "r", mode: "categorical" } } }));
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "", mode: "numeric" } } }));
  await userEvent.type(screen.getByLabelText("Champ taille"), "m");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { size: { field: "m" } } }));
});

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:1");
  expect(view).toHaveTextContent("url:https://fs/parcs/items.json");
});

test("map widget renders an empty map when no source is bound", async () => {
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:0");
});

test("map declares extentChanged/itemSelected events and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toEqual(["extentChanged", "itemSelected"]);
  expect(getWidget("map")!.actions).toEqual(expect.arrayContaining(["flyTo", "highlight"]));
});

test("map emits extentChanged when the view moves", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "extentChanged", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("mapview"));
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] });
});

test("map flyTo action flies to a selected record's point", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await screen.findByTestId("mapview");
  bus.emit("list1", "itemSelected", { id: 1, properties: {}, geometry: { type: "Point", coordinates: [5, 6] } });
  expect(flyToSpy).toHaveBeenCalledWith({ center: [5, 6], zoom: 12 });
});

test("map emits itemSelected when a feature is clicked", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "itemSelected", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } });
});

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
      <ExtentProbe />
    </AnalyticsContextProvider>,
  ));
  const view = await screen.findByTestId("mapview");
  vi.useFakeTimers();
  try {
    fireEvent.click(view);
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.getByText("extent:10,20,30,40")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  ));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText("cf:id=1")).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: { loading: false, error: false, records: [], datasetId: "ds1", url: "https://core/collections/geo/items" } } as unknown as WidgetContext;
  render(withClient(<ExplorerProvider enabled><Map props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>));
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("colors features by a categorical field once the domain query resolves", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { groupBy?: string } }) => {
    if (source.query?.groupBy === "region") {
      return [{ id: "Nord", properties: { value: 2 } }, { id: "Sud", properties: { value: 1 } }];
    }
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  await waitFor(() => expect(view.textContent).toContain('"fill-color"'));
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("#2563eb");
  expect(view.textContent).toContain("#dc2626");
});

test("colors and sizes point features by numeric fields once both domain queries resolve", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { measures?: { field: string }[] } }) => {
    const field = source.query?.measures?.[0]?.field;
    if (field === "valeur") return [{ id: "s", properties: { min: 0, max: 100 } }];
    if (field === "montant") return [{ id: "s", properties: { min: 5, max: 25 } }];
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/points/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "valeur", mode: "numeric" }, size: { field: "montant" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  // Both domain queries (color, size) resolve independently — wait for both
  // paint keys inside the same waitFor so a flush of just one doesn't pass
  // the assertion prematurely.
  await waitFor(() => {
    expect(view.textContent).toContain('"circle-radius"');
    expect(view.textContent).toContain('"circle-color"');
  });
  expect(view.textContent).toContain("renderAs:circle");
});

test("shows no symbology legend when no encoding is configured", () => {
  const ctx = { mode: "runtime", data: state({ url: "https://fs/communes/items.json" }) } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  expect(screen.queryByText("Nord")).not.toBeInTheDocument();
});

test("shows a categorical symbology legend once the color domain resolves", async () => {
  const queryDataSource = vi.fn(async () => [{ id: "Nord", properties: { value: 1 } }, { id: "Sud", properties: { value: 1 } }]);
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  expect(await screen.findByText("Nord")).toBeInTheDocument();
  expect(screen.getByText("Sud")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npm run test -- mapWidget.test.tsx`
Expected: FAIL — every test that renders `<Map .../>` throws `useItemClient must be used within an ItemClientProvider` (the widget doesn't call `useItemClient`/`useQuery` yet, so `withClient`'s providers are inert, but more importantly `PropsPanel` has no color/size fields yet and `encodings`-related tests find nothing to assert on).

- [ ] **Step 3: Write the widget implementation**

Replace the full contents of `shell/src/builder/widgets/mapWidget.tsx` with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { buildLegend, buildMapPaint, detectGeometryKind } from "./mapSymbology";
import type { ColorDomain, LegendSpec, MapEncodings, SizeDomain } from "./mapSymbology";
import type { ItemClient, MapConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function centerFromPayload(p: unknown): [number, number] | null {
  const rec = p as { center?: [number, number]; geometry?: { type?: string; coordinates?: number[] } } | undefined;
  if (rec?.center) return rec.center;
  const g = rec?.geometry;
  if (g?.type === "Point" && Array.isArray(g.coordinates)) return [g.coordinates[0], g.coordinates[1]];
  return null;
}

function geometryFromPayload(p: unknown): unknown | null {
  return (p as { geometry?: unknown } | undefined)?.geometry ?? null;
}

// Bornes min/max d'un champ numérique, interrogées séparément de la
// DataSource "features" qui alimente le rendu — même patron que
// sliderFilter.tsx (measures min/max sur une source "statistics").
function useNumericDomain(client: ItemClient, datasetId: string | undefined, field: string, active: boolean) {
  return useQuery({
    queryKey: ["map-numeric-domain", datasetId, field],
    queryFn: async (): Promise<SizeDomain> => {
      const rows = await client.queryDataSource({
        id: `map-domain-${datasetId}-${field}`, type: "statistics", service: "core",
        layer: "", datasetId, query: { measures: [{ field, agg: "min" }, { field, agg: "max" }] },
      });
      const properties = rows[0]?.properties ?? {};
      return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
    },
    enabled: active && Boolean(datasetId && field),
  });
}

function MapSymbologyLegend({ legend }: { legend: LegendSpec }) {
  return (
    <div className="absolute bottom-2 right-2 z-10 flex flex-col gap-2 rounded-md bg-white/90 p-2 text-xs shadow">
      {legend.color?.kind === "categorical" && (
        <ul>
          {legend.color.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: e.color }} />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "numeric" && (
        <div>
          <div className="h-2 w-24 rounded"
            style={{ background: `linear-gradient(to right, ${legend.color.colorLow}, ${legend.color.colorHigh})` }} />
          <span>{legend.color.min} – {legend.color.max}</span>
        </div>
      )}
      {legend.size && (
        <div className="flex items-end gap-2">
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMin, height: legend.size.radiusMin }} />
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMax, height: legend.size.radiusMax }} />
          <span>{legend.size.min} – {legend.size.max}</span>
        </div>
      )}
    </div>
  );
}

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const setEncodings = (patch: MapEncodings) => onChange({ ...props, encodings: { ...encodings, ...patch } });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className={labelCls}>Champ couleur
            <input aria-label="Champ couleur" className={inputCls}
              value={String(encodings.color?.field ?? "")}
              onChange={(e) => setEncodings({ color: { field: e.target.value, mode: encodings.color?.mode ?? "categorical" } })} />
          </label>
          <label className={labelCls}>Type de couleur
            <select aria-label="Type de couleur" className={inputCls}
              value={encodings.color?.mode ?? "categorical"}
              onChange={(e) => setEncodings({ color: { field: encodings.color?.field ?? "", mode: e.target.value as "categorical" | "numeric" } })}>
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          <label className={labelCls}>Champ taille
            <input aria-label="Champ taille" className={inputCls}
              value={String(encodings.size?.field ?? "")}
              onChange={(e) => setEncodings({ size: { field: e.target.value } })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });

      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const datasetId = ctx.data?.datasetId;
      const colorField = encodings.color?.field ?? "";
      const colorMode = encodings.color?.mode ?? "categorical";
      const sizeField = encodings.size?.field ?? "";

      const categoricalQuery = useQuery({
        queryKey: ["map-categorical-domain", datasetId, colorField],
        queryFn: async (): Promise<string[]> => {
          const rows = await client.queryDataSource({
            id: `map-domain-${datasetId}-${colorField}`, type: "statistics", service: "core",
            layer: "", datasetId, query: { groupBy: colorField },
          });
          return rows.map((r) => String(r.id));
        },
        enabled: Boolean(datasetId && colorField && colorMode === "categorical"),
      });
      const numericColorQuery = useNumericDomain(client, datasetId, colorField, colorMode === "numeric");
      const sizeQuery = useNumericDomain(client, datasetId, sizeField, true);

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

      const colorDomain: ColorDomain | null = !colorField
        ? null
        : colorMode === "categorical"
          ? (categoricalQuery.data ? { kind: "categorical", values: categoricalQuery.data } : null)
          : (numericColorQuery.data ? { kind: "numeric", ...numericColorQuery.data } : null);
      const sizeDomain: SizeDomain | null = sizeField && sizeQuery.data ? sizeQuery.data : null;
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      const { renderAs, paint } = buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind);
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind);

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url, renderAs, paint }]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""));
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npm run test -- mapWidget.test.tsx`
Expected: PASS — 15 tests green.

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS — all existing suites remain green, plus `mapSymbology.test.ts` (Task 1), the extended `MapView.test.tsx` (Task 2) and the rewritten `mapWidget.test.tsx`.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/builder/widgets/mapWidget.tsx src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): map widget colors and sizes features from dataset encodings, with a legend (SP-14h)"
```

---

