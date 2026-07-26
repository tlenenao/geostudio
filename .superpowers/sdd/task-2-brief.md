### Task 2: `derivePatch` — range branch

**Files:**
- Modify: `shell/src/lib/analyticsPatch.ts:26-33` (the `crossFilter` block inside `derivePatch`)
- Test: `shell/src/lib/analyticsPatch.test.ts`

**Interfaces:**
- Consumes: `CrossFilterValue` from Task 1 (`../builder/AnalyticsContext`).
- Produces: no new exports — `derivePatch`'s existing signature and behavior for scalar/array values is unchanged; only a new range case is added.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/lib/analyticsPatch.test.ts`:

```ts
test("uses field__gte/field__lte for a range cross-filter value", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ score__gte: "10", score__lte: "50" });
});

test("excludes a range cross-filter patch when this source is the origin", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-1" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: FAIL — current code does `patch[crossFilter.field] = crossFilter.value` for a non-array value, so the range object gets assigned directly to `score` instead of producing `score__gte`/`score__lte`.

- [ ] **Step 3: Implement**

In `shell/src/lib/analyticsPatch.ts`, replace the `crossFilter` block (currently):

```ts
  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    else patch[crossFilter.field] = crossFilter.value;
  }
```

with:

```ts
  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) {
      patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    } else if (typeof crossFilter.value === "object") {
      patch[`${crossFilter.field}__gte`] = crossFilter.value.from;
      patch[`${crossFilter.field}__lte`] = crossFilter.value.to;
    } else {
      patch[crossFilter.field] = crossFilter.value;
    }
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: PASS, all tests (the 2 new ones plus the full pre-existing suite for scalar/array/time/extent combinations).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/lib/analyticsPatch.ts src/lib/analyticsPatch.test.ts
git commit -m "feat(shell): derivePatch translates a range cross-filter to __gte/__lte (SP-14c)"
```

---

