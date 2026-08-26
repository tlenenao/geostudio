## Task 8: Shell — wire `LayersPanel.tsx`

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: `MapSymbologyEditor` (Task 7); `client.queryDataSource`,
  `client.sampleCollectionField` (Task 5).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/map/LayersPanel.test.tsx`:

```tsx
test("a vector layer with a collectionId exposes the symbology editor and can recompute a numeric domain", async () => {
  const onChange = vi.fn();
  const client = {
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [{ name: "pop" }] }),
    queryDataSource: vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]),
    sampleCollectionField: vi.fn(),
  } as unknown as ItemClient;
  const vectorLayer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "u",
    sourceLayer: "communes",
    collectionId: "communes",
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={[vectorLayer]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await userEvent.type(screen.getByLabelText("Champ couleur"), "pop");
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(client.queryDataSource).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "statistics",
      service: "core",
      layer: "communes",
      query: expect.objectContaining({ measures: expect.any(Array) }),
    }),
  );
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      symbology: expect.objectContaining({
        color: expect.objectContaining({ domain: { kind: "numeric", min: 0, max: 100 } }),
      }),
    }),
  ]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx -t "symbology editor"`
Expected: FAIL — no symbology editor rendered yet.

- [ ] **Step 3: Wire it**

In `shell/src/map/LayersPanel.tsx`, add a `LayerSymbologyEditor` wrapper
component mirroring the existing `LayerPopupEditor` (same file):

```tsx
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
  if (!collectionId) return null; // external tiles / plain GeoJSON feature layer: no collection to query
  return (
    <MapSymbologyEditor
      value={layer.symbology}
      availableFields={schema.data?.fields.map((f) => f.name) ?? []}
      themeColors={undefined} // no Theme on a standalone MapConfig (spec §1)
      runStatistics={(query) =>
        client.queryDataSource({
          id: `map-symbology-${collectionId}`,
          type: "statistics",
          service: "core",
          layer: collectionId,
          query,
        })
      }
      sampleField={(field, limit) => client.sampleCollectionField(collectionId, field, limit)}
      onChange={(symbology) => onChangeLayer({ ...layer, symbology })}
    />
  );
}
```

Mount it right after the existing `LayerPopupEditor` in the layer `<li>`:

```tsx
            {(layer.kind === "vector" || layer.kind === "feature") && (
              <div className="basis-full pl-2">
                <LayerPopupEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
                <LayerSymbologyEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
              </div>
            )}
```

Import `MapSymbologyEditor` at the top of the file.

Note: for a `"feature"` kind layer (no `collectionId` ever, per its type),
`LayerSymbologyEditor` returns `null` — a `feature` layer's data comes from
an arbitrary GeoJSON URL, not a queryable collection, so there is no
`runStatistics` source for it in `LayersPanel` (the same layer kind used
inside `mapWidget.tsx` DOES get symbology, Task 10, because there
`runStatistics` resolves through the widget's own `datasetId`, not through
`LayersPanel`'s collection-only path). Document this explicitly as a scoped
limitation, not a bug: standalone `feature` layers keep the pre-existing
`paint`-only manual path.

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS, all tests (5 existing + 1 new).

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): branche MapSymbologyEditor sur les couches vector de l'éditeur de cartes
EOF
)"
```

---

