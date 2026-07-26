### Task 1: `AnalyticsContext` — range cross-filter value + `clearCrossFilter`

**Files:**
- Modify: `shell/src/builder/AnalyticsContext.tsx` (whole file is 91 lines; changes touch lines 4, 16-27, 58-70, 88-91)
- Test: `shell/src/builder/AnalyticsContext.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `export type CrossFilterValue = string | string[] | { from: string; to: string }`; `CrossFilterEntry.value: CrossFilterValue` (was `string | string[]`); `export function useClearCrossFilter(): (datasetId: string) => void`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/builder/AnalyticsContext.test.tsx`, inside the existing `Probe` component add two buttons (import `useClearCrossFilter` at the top alongside the other hooks):

```tsx
import {
  AnalyticsContextProvider, useAnalyticsContext, useClearCrossFilter, useSetCrossFilter, useSetExtent, useSetTimeRange,
} from "./AnalyticsContext";

function Probe() {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  const clearCrossFilter = useClearCrossFilter();
  return (
    <div>
      <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>
      <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>
      <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>set-time</button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
      <button onClick={() => setCrossFilter("ds1", "period", { from: "2026-01-01", to: "2026-02-01" }, "src1")}>set-cf-range</button>
      <button onClick={() => clearCrossFilter("ds1")}>clear-cf</button>
    </div>
  );
}
```

Append these tests (after the existing `"setCrossFilter toggles..."` test, still outside the `describe("extent debounce", ...)` block):

```tsx
test("setCrossFilter accepts a {from,to} range value", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf-range"));
  expect(screen.getByText(/"ds1":\{"field":"period","value":\{"from":"2026-01-01","to":"2026-02-01"\},"originSourceId":"src1"\}/)).toBeInTheDocument();
});

test("clearCrossFilter removes the entry for that dataset", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/"ds1":/)).toBeInTheDocument();
  await userEvent.click(screen.getByText("clear-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});

test("clearCrossFilter is a no-op when interactions is not 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="manual"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("clear-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: FAIL — `setCrossFilter` rejects/mistypes the range value (TS) and `useClearCrossFilter` does not exist (import error).

- [ ] **Step 3: Implement**

Replace line 4 of `shell/src/builder/AnalyticsContext.tsx`:

```ts
export type CrossFilterValue = string | string[] | { from: string; to: string };
export type CrossFilterEntry = { field: string; value: CrossFilterValue; originSourceId: string };
```

Replace lines 16-27 (the two type aliases through `sameCrossFilterValue`):

```ts
type SetTimeRange = (range: { from: string; to: string } | null) => void;
type SetExtent = (bbox: [number, number, number, number] | null) => void;
type SetCrossFilter = (datasetId: string, field: string, value: CrossFilterValue, originSourceId: string) => void;
type ClearCrossFilter = (datasetId: string) => void;

const AnalyticsStateContext = createContext<AnalyticsContextState>(EMPTY_ANALYTICS_CONTEXT);
const AnalyticsSettersContext = createContext<{
  setTimeRange: SetTimeRange; setExtent: SetExtent; setCrossFilter: SetCrossFilter; clearCrossFilter: ClearCrossFilter;
}>({
  setTimeRange: () => {}, setExtent: () => {}, setCrossFilter: () => {}, clearCrossFilter: () => {},
});

function sameCrossFilterValue(a: CrossFilterValue, b: CrossFilterValue): boolean {
  return typeof a === "string" && typeof b === "string" ? a === b : JSON.stringify(a) === JSON.stringify(b);
}
```

Replace lines 58-70 (from `const setCrossFilter = ...` through the `setters` memo):

```ts
  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const clearCrossFilter = useCallback<ClearCrossFilter>((datasetId) => {
    if (!active) return;
    setState((prev) => {
      if (!prev.crossFilter[datasetId]) return prev;
      const nextCrossFilter = { ...prev.crossFilter };
      delete nextCrossFilter[datasetId];
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const setters = useMemo(
    () => ({ setTimeRange, setExtent, setCrossFilter, clearCrossFilter }),
    [setTimeRange, setExtent, setCrossFilter, clearCrossFilter],
  );
```

Replace lines 88-91 (the final export block) — append the new hook after `useSetCrossFilter`:

```ts
export function useSetCrossFilter(): SetCrossFilter {
  return useContext(AnalyticsSettersContext).setCrossFilter;
}
export function useClearCrossFilter(): ClearCrossFilter {
  return useContext(AnalyticsSettersContext).clearCrossFilter;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: PASS, all tests including the 3 new ones and the pre-existing ones (toggle, debounce, no-provider default).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/AnalyticsContext.tsx src/builder/AnalyticsContext.test.tsx
git commit -m "feat(shell): cross-filter range value + clearCrossFilter setter (SP-14c)"
```

---

