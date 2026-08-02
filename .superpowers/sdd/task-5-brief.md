### Task 5: Shell — `DataSourcePanel` supports a comma-separated multi-field `groupBy` and a `bins` field

**Files:**
- Modify: `shell/src/builder/DataSourcePanel.tsx:76-93`
- Test: `shell/src/builder/DataSourcePanel.test.tsx`

**Interfaces:**
- Produces: new pure helper `parseGroupBy(raw: string): string | string[]` (exported for the test, or kept module-private and covered through the component test below — kept module-private here, consistent with the file's existing lack of exports beyond `DataSourcePanel`). Typing a value with no comma keeps `query.groupBy` a plain `string` (byte-for-byte unchanged behavior); typing a comma-separated value sets it to a `string[]`. New "Nombre de classes" numeric input writes `query.bins`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/DataSourcePanel.test.tsx` (needs `fireEvent` alongside the existing `render`/`screen`/`within` import):

```tsx
test("a comma-separated group-by becomes a string array; a single field stays a string", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} }];
  const onChange = vi.fn();
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Grouper par (source d1)"), { target: { value: "origin,destination" } });
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toEqual(["origin", "destination"]);

  const withArray: DataSource[] = [{ ...sources[0], query: { groupBy: ["origin", "destination"] } }];
  rerender(<DataSourcePanel sources={withArray} onChange={onChange} />);
  expect(screen.getByLabelText("Grouper par (source d1)")).toHaveValue("origin,destination");
});

test("edits the histogram bin count on a statistics source", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nombre de classes (source d1)"), "8");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.bins).toBe(8);
});
```

Update the file's import line to add `fireEvent`:

```tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx -t "comma-separated|bin count"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/builder/DataSourcePanel.tsx`, add a module-level helper right after the `type Measure = ...` line:

```tsx
// A single field ("region") is passed through unchanged; a comma-separated
// value ("origin,destination") becomes a string[] — the multi-field tidy
// groupBy that sankey/treemap/sunburst need (SP-14f).
function parseGroupBy(raw: string): string | string[] {
  const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
  return parts.length > 1 ? parts : raw;
}

function groupByDisplayValue(groupBy: unknown): string {
  return Array.isArray(groupBy) ? groupBy.join(",") : String(groupBy ?? "");
}
```

Replace the "Grouper par" input (lines 76-78) with:

```tsx
                <input aria-label={`Grouper par (source ${s.id})`} placeholder="grouper par (axe X, virgule = plusieurs niveaux)"
                  className={inputCls}
                  value={groupByDisplayValue(s.query.groupBy)}
                  onChange={(e) => patchQuery(s.id, { groupBy: parseGroupBy(e.target.value) })} />
```

Add a "Nombre de classes" numeric input right after the "Champ agrégé" input (after line 94, still inside the `<div className="flex gap-1">` sibling block, as its own line below that div):

```tsx
                <input aria-label={`Nombre de classes (source ${s.id})`} type="number" min={1} max={100}
                  placeholder="classes (histogramme)" className={inputCls}
                  value={String(s.query.bins ?? "")}
                  onChange={(e) => patchQuery(s.id, { bins: e.target.value ? Number(e.target.value) : undefined })} />
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: PASS — new tests plus full existing file green (existing "edits a statistics source's group-by and split" test still passes: typing a single char has no comma, `parseGroupBy` returns it unchanged).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx
git commit -m "feat(shell): DataSourcePanel supports multi-field groupBy and a histogram bin count (SP-14f)"
```

---

