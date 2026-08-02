### Task 6: Shell — `chartOption.ts`: `encodings`/`bins` types, funnel and histogram

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts:6-20` (`ChartProps`), `shell/src/builder/widgets/chartOption.ts:127-151` (add branches before the fallback bar/line/area/scatter block)
- Test: `shell/src/builder/widgets/chartOption.test.ts`

**Interfaces:**
- Produces: `ChartProps.encodings?: { source?: string; target?: string; levels?: string[]; value?: string }` and `ChartProps.bins?: number`. `buildOption` handles `chartType === "funnel"` (reuses `categoryField`/`valueField`) and `chartType === "histogram"` (reads `bucketStart`/`bucketEnd`/`count` off each row — the shape `_run_binned_histogram` (Task 3) produces).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
const histogramRows: DataRecord[] = [
  { id: "0", properties: { bucketIndex: 0, bucketStart: 0, bucketEnd: 5, count: 3 } },
  { id: "2", properties: { bucketIndex: 2, bucketStart: 10, bucketEnd: 15, count: 7 } },
];

test("funnel builds one funnel series from category/value fields", () => {
  const funnelRows: DataRecord[] = [
    { id: "1", properties: { stage: "Visite", value: 100 } },
    { id: "2", properties: { stage: "Panier", value: 40 } },
  ];
  const opt = buildOption({ chartType: "funnel", categoryField: "stage", valueField: "value" }, funnelRows);
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("funnel");
  expect(series(opt)[0].data).toEqual([{ name: "Visite", value: 100 }, { name: "Panier", value: 40 }]);
});

test("histogram renders one bar series labeled by bucket bounds", () => {
  const opt = buildOption({ chartType: "histogram" }, histogramRows);
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("bar");
  expect(series(opt)[0].data).toEqual([3, 7]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["0–5", "10–15"]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "funnel|histogram"`
Expected: FAIL (unknown chart types fall through to the default bar/line branch, wrong shape)

- [ ] **Step 3: Implement**

In `shell/src/builder/widgets/chartOption.ts`, replace the `ChartProps` type (lines 6-20):

```ts
export type ChartProps = {
  dataSourceId?: string;
  chartType?: string; // bar|line|area|scatter|pie|doughnut|radar|heatmap|gauge|boxplot|sankey|treemap|sunburst|funnel|histogram
  categoryField?: string;
  valueField?: string; // measure key for pie/gauge/funnel/histogram (defaults to first series)
  stack?: boolean;
  legend?: boolean;
  zoom?: boolean;
  xAxisType?: string; // category|value|time|log
  yAxisType?: string; // value|log|category
  yAxisFormat?: string; // any non-empty value → grouped number formatting
  yAxisUnit?: string;
  title?: string;
  advancedOption?: string; // raw ECharts option JSON, deep-merged last
  // Field-role mapping used only by sankey and treemap/sunburst — every
  // other chart type keeps categoryField/valueField (SP-14f §3).
  encodings?: { source?: string; target?: string; levels?: string[]; value?: string };
  bins?: number; // histogram bin count, default 10
};
```

Add a small formatting helper right after `valueFormatter` (after line 59):

```ts
function round2(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(n);
}
```

In `buildOption`, insert two new branches right before the `// bar | line | area | scatter` fallback comment (before line 136):

```ts
  if (type === "funnel") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      series: [{
        type: "funnel",
        data: rows.map((row) => ({ name: String(row[catKey] ?? ""), value: num(row[valueKey]) })),
      }],
    });
  }

  if (type === "histogram") {
    const labels = rows.map((row) => `${round2(Number(row.bucketStart))}–${round2(Number(row.bucketEnd))}`);
    const counts = rows.map((row) => num(row.count));
    return finalize(props, {
      ...base,
      xAxis: { type: "category", data: labels },
      yAxis,
      series: [{ type: "bar", name: "Effectif", data: counts }],
    });
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS — new tests plus full existing file green.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chartOption gains funnel and server-binned histogram (SP-14f)"
```

---

