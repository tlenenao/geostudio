## Task 11: Shell — wire `mapWidget.tsx` onto `LayerSymbology`

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `MapSymbologyEditor` (Task 7), `symbologyToPaintInputs`,
  `LayerSymbology` (Task 6), `theme` prop on `PropsPanel` and `ctx.theme`
  on `WidgetContext` (both from Task 10).
- Removes: `props.encodings`, `MapEncodings` import for that purpose,
  `useNumericDomain`, the two domain `useQuery`s in `Component`.

This is the breaking change documented in the spec (§2, §7): any
already-saved app config with `props.encodings` loses its symbology on next
load — it is not migrated.

- [ ] **Step 1: Read the current file in full again**

It was already read in full during planning (reproduced above in this
plan's research) — re-read it live before editing, since this task rewrites
most of `PropsPanel` and `Component`.

- [ ] **Step 2: Update the failing/changed tests first**

In `shell/src/builder/widgets/mapWidget.test.tsx`, find every test that sets
`props.encodings` or asserts on the domain `useQuery` calls (`groupBy`/
`min`/`max` statistics queries triggered by `Component` itself) — these
tests describe the **old** behavior being removed. Rewrite them to use
`props.symbology` instead, and to assert `Component` does **not** call
`client.queryDataSource` at all (no live domain fetch at render):

```tsx
test("Component renders paint from frozen props.symbology, without querying any domain", () => {
  const client = {
    queryDataSource: vi.fn(), // must NOT be called by Component
    getAuthToken: () => undefined,
    getCoreUrl: () => "https://core.test",
  } as unknown as ItemClient;
  // ... render the widget's Component with props.symbology set and a
  // ctx.data.url present, following this file's existing render helper ...
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("PropsPanel mounts MapSymbologyEditor with theme from props", () => {
  // ... render PropsPanel with theme={{ colors: { primary: "#2563eb" } }},
  // assert the "Thème du site" option is present in the rendered select ...
});

test("Component resolves the theme-primary palette from ctx.theme at render time", () => {
  // render the widget's Component with props.symbology.color.palette ===
  // "theme-primary" and ctx.theme = { colors: { primary: "#2563eb" } };
  // assert the resulting paint's interpolate/step expression ends on
  // "#2563eb" (the high stop of resolvePalette("theme-primary", ...)),
  // not the "categorical-a"/"sequential-blue" hardcoded defaults — this is
  // the exact bug this plan's self-review caught (Task 10): without
  // ctx.theme threaded through, this would silently render wrong colors.
});
```

Fill in the exact render helper by copying this file's existing
`PropsPanel`/`Component` render setup (it already exists for the
`encodings`-based tests being replaced) rather than inventing new
scaffolding.

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL — old tests reference removed behavior; new tests fail
against the not-yet-updated implementation.

- [ ] **Step 4: Rewrite `PropsPanel`**

Replace the widget's `PropsPanel` entirely:

```tsx
    PropsPanel: ({ props, onChange, dataSources, theme }) => {
      const client = useItemClient();
      const dataSourceId = String(props.dataSourceId ?? "");
      const dataSource = dataSources.find((d) => d.id === dataSourceId);
      const datasetId = dataSource?.datasetId;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect
            value={dataSourceId}
            dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })}
          />
          <MapSymbologyEditor
            value={props.symbology as LayerSymbology | undefined}
            availableFields={[]} // PropsPanel has no schema (registry.ts) — same PopupEditor precedent
            themeColors={theme?.colors}
            runStatistics={(query) =>
              client.queryDataSource({
                id: `map-domain-${datasetId}`,
                type: "statistics",
                service: "core",
                layer: "",
                datasetId,
                query,
              })
            }
            sampleField={async () => {
              throw new Error("Jenks sur le widget carte nécessite un collectionId résolu — non câblé");
            }}
            onChange={(symbology) => onChange({ ...props, symbology })}
          />
          <PopupEditor
            value={props.popup as PopupConfig | undefined}
            availableFields={[]}
            onChange={(popup) => onChange({ ...props, popup })}
          />
        </div>
      );
    },
```

Note the `sampleField` stub: `mapWidget.tsx`'s `runStatistics` resolves
through `datasetId` (not a direct `collectionId`), and `sampleCollectionField`
on `ItemClient` takes a `collectionId`. Resolving a `datasetId` to its
underlying `collectionId` for this one call requires the same
`resolveDataset`-style lookup `itemClient.ts` already does internally for
`queryDataSource` — **but that resolution is private to `itemClient.ts`,
not exposed on the `ItemClient` interface**. Rather than exposing an
internal implementation detail through the public interface for one call
site, **Jenks is out of scope for the widget's color field in this task**:
the "Seuils naturels (Jenks)" option in `MapSymbologyEditor`'s method
selector will throw if chosen from the widget's `PropsPanel`. Write one
more test proving this explicitly:

```tsx
test("choosing Jenks from the widget's PropsPanel surfaces an error instead of hanging", async () => {
  // select "jenks" as the classification method, click "Recalculer les
  // classes", assert an error is shown (not a silent hang or a crash) —
  // MapSymbologyEditor's recomputeColor already wraps the call and resets
  // `busy` in its `finally`, so the button re-enables; add an error string
  // state to MapSymbologyEditor if none exists yet (check Task 7's
  // implementation — if recomputeColor has no catch, add one there instead
  // of duplicating it here, since both hosts share the component).
});
```

Go back to `MapSymbologyEditor.tsx` (Task 7) and add a caught-error display,
since this is exactly the kind of thing "no placeholders" rules out leaving
implicit:

```tsx
  const [error, setError] = useState<string | null>(null);
  async function recomputeColor() {
    if (!color?.field) return;
    setBusy("color");
    setError(null);
    try {
      const domain = await computeColorDomain(/* ... */);
      onChange(/* ... */);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }
```

And render `{error && <p role="alert" className="text-xs text-red-600">{error}</p>}`
near the recompute button. Add one test for this in Task 7's test file too
(retroactively — this is a real gap the two-task split surfaced, fix it
where the component actually lives):

```tsx
test("a failing recompute surfaces an error instead of hanging silently", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("boom"));
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});
```

- [ ] **Step 5: Rewrite `Component`**

Replace the domain-fetching section and paint/legend construction:

```tsx
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

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

      const symbology = props.symbology as LayerSymbology | undefined;
      const { encodings, colorDomain, sizeDomain, palette } = symbologyToPaintInputs(
        symbology,
        ctx.theme?.colors,
      );
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      const { renderAs, paint } = buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette);
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind, palette);

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [
              {
                id: `ds-${String(props.dataSourceId)}`,
                title: "Données",
                visible: true,
                kind: "feature",
                url,
                renderAs,
                paint,
                popup: props.popup as PopupConfig | undefined,
              },
            ]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu
            datasetId={ctx.data?.datasetId}
            dataSourceId={String(props.dataSourceId ?? "")}
            resolvedSource={ctx.data?.resolvedSource}
            hasGeometry={ctx.data?.hasGeometry}
          />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn)
                  setCrossFilter(
                    datasetId,
                    pkColumn,
                    String(record.id),
                    String(props.dataSourceId ?? ""),
                    record.geometry,
                  );
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
```

Remove `useNumericDomain`, the `useQuery` import if now unused elsewhere in
the file (check — `Component` no longer uses it, but confirm nothing else
in the file does before deleting the import), `MapEncodings`/`ColorDomain`/
`SizeDomain` imports (replaced by `LayerSymbology`/`symbologyToPaintInputs`),
and update the top-of-file import block:

```tsx
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { buildLegend, buildMapPaint, detectGeometryKind, symbologyToPaintInputs } from "./mapSymbology";
import type { LayerSymbology, LegendSpec } from "./mapSymbology";
import type { ItemClient, MapConfig, PopupConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";
import { PopupEditor } from "../../map/PopupEditor";
import { MapSymbologyEditor } from "../../map/MapSymbologyEditor";
```

(`lazy`/`Suspense`/`useRef` from `"react"` stay; `ItemClient` type import
stays only if still referenced — check before keeping it.)

Update `MapSymbologyLegend` to render the new `"classed"` legend kind
(alongside the existing `"categorical"`/`"numeric"` branches):

```tsx
      {legend.color?.kind === "classed" && (
        <ul>
          {legend.color.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: c.color }} />
              {c.from.toFixed(1)} – {c.to.toFixed(1)}
            </li>
          ))}
        </ul>
      )}
```

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS, all tests.

- [ ] **Step 7: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green, count reflecting removed old tests + added new ones.

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte utilise LayerSymbology au lieu d'encodings

Changement cassant assumé (spec §2/§7) : une app déjà publiée avec une
symbologie de widget carte perd sa configuration au prochain
chargement. Jenks non câblé sur cette surface (pas de collectionId
direct) — méthode refusée avec une erreur visible plutôt qu'un hang.
Component ne fait plus aucun appel réseau de domaine à chaque rendu.
EOF
)"
```

---

