## Task 5: Shell — types partagés (`LayerSymbology`, `MapLayer.symbology`, `ItemClient.sampleCollectionField`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`
- Test: `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient` gains `sampleCollectionField(collectionId: string,
  field: string, limit: number): Promise<number[]>`.

(`MapLayer.symbology: LayerSymbology` is added later, in Task 6 Step 11 —
`LayerSymbology` is defined in that same task, in `mapSymbology.ts`, so
adding the field to `MapLayer` right there avoids a forward reference to a
type that doesn't exist yet. This task only handles
`sampleCollectionField`, which has no dependency on Task 6.)

- [ ] **Step 1: Write the failing test for `sampleCollectionField`**

Add to `shell/src/api/itemClient.test.ts` (find the existing `describe`/test
block that exercises `queryDataSource`'s statistics path, to reuse its
`fetchMock`/`coreUrl` setup):

```ts
test("sampleCollectionField posts sample+field and returns bare numeric values", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ categoryKey: "value", rows: [{ value: 1 }, { value: 2.5 }] }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  const values = await client.sampleCollectionField("communes", "population", 500);

  expect(values).toEqual([1, 2.5]);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://core.test/collections/communes/aggregate");
  expect(JSON.parse(init.body as string)).toEqual({ field: "population", sample: 500 });
});
```

Adjust `createItemClient`'s exact constructor signature and the `fetchMock`
setup style to match whatever the file's existing tests actually do (read
the nearest existing `queryDataSource`/statistics test in that file first —
this sketch shows the shape of the assertions, not a verbatim copy of test
scaffolding you have not read).

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t sampleCollectionField`
Expected: FAIL — `client.sampleCollectionField is not a function`.

- [ ] **Step 3: Add the interface method**

In `shell/src/api/types.ts`, in the `ItemClient` interface, right after
`listLayerSources`:

```ts
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
  sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]>;
```

- [ ] **Step 4: Implement it in `itemClient.ts`**

In `shell/src/api/itemClient.ts`, add `sample` to the existing `STAT_KEYS`
set:

```ts
const STAT_KEYS = new Set([
  "groupBy",
  "split",
  "agg",
  "field",
  "measures",
  "bbox",
  "bucket",
  "bins",
  "sample",
  "p",
]);
```

And in `buildAggregateBody`, right after the `bins` line:

```ts
  if (query.bins) body.bins = Number(query.bins);
  if (query.sample) body.sample = Number(query.sample);
```

Then add the method itself, right after `queryDataSource` in the returned
client object (same file, same `request<T>` helper already used
everywhere):

```ts
    async sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]> {
      const data = await request<{ categoryKey: string | string[]; rows: { value: number }[] }>(
        "POST",
        `/collections/${collectionId}/aggregate`,
        { field, sample: limit },
      );
      return data.rows.map((r) => Number(r.value));
    },
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t sampleCollectionField`
Expected: PASS.

- [ ] **Step 6: Implement `StaticItemClient`'s explicit rejection**

In `shell/src/staticExport/StaticItemClient.ts`, add (near
`exportDataSource`'s `unsupported()` entry, same style):

```ts
    async sampleCollectionField(_collectionId: string, _field: string, _limit: number) {
      return unsupported();
    },
```

Add a matching test in `shell/src/staticExport/StaticItemClient.test.ts`
(mirror whichever existing `unsupported()` test is there, e.g. for
`exportDataSource`):

```ts
test("sampleCollectionField rejects — no backend in a static export", async () => {
  const client = createStaticItemClient(EMPTY_CONFIG); // use whatever fixture name the file already defines
  await expect(client.sampleCollectionField("c", "f", 10)).rejects.toThrow(
    "Non disponible dans un export statique",
  );
});
```

- [ ] **Step 7: Run the full shell suite**

Run: `cd shell && npx vitest run && npm run build`
Expected: PASS, no `ItemClient` implementer left incomplete (TypeScript
would already fail `npm run build` if `StaticItemClient.ts` were missing the
method — this is the mechanism SP-18a relies on, verify it actually catches
it by checking the diff includes `StaticItemClient.ts`).

- [ ] **Step 8: Gates + commit**

Run: `cd shell && npm run lint && npm run format:check`

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute ItemClient.sampleCollectionField

Premier appelant : le calcul des seuils naturels (Jenks) côté
MapSymbologyEditor (SP-25). Rejeté explicitement en export statique,
même précédent que les autres méthodes réseau de StaticItemClient.
EOF
)"
```

---

