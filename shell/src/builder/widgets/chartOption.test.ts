// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { buildCompareOption, buildOption, resolveClickFilter } from "./chartOption";
import type { DataRecord } from "../../api/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const series = (o: unknown): any[] => {
  const s = (o as { series?: unknown }).series;
  return Array.isArray(s) ? s : s ? [s] : [];
};

const wide: DataRecord[] = [
  { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
  { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 7 } },
];

test("bar builds one series per non-category column", () => {
  const opt = buildOption({ chartType: "bar", categoryField: "region" }, wide);
  expect(series(opt)).toHaveLength(2);
  expect(series(opt)[0].type).toBe("bar");
  expect(series(opt).map((s) => s.name)).toEqual(["2025", "2026"]);
  // dataset carries the rows so encode can map category → value.
  expect((opt as { dataset?: { source?: unknown[] } }).dataset?.source).toHaveLength(2);
});

test("defaults the category to the first non-numeric column", () => {
  const opt = buildOption({ chartType: "bar" }, wide);
  expect(series(opt)).toHaveLength(2);
  expect(series(opt).map((s) => s.name)).toEqual(["2025", "2026"]);
});

test("stacked bars set a shared stack id", () => {
  const opt = buildOption({ chartType: "bar", categoryField: "region", stack: true }, wide);
  expect(series(opt)[0].stack).toBeTruthy();
  expect(series(opt)[0].stack).toBe(series(opt)[1].stack);
});

test("area is a line series with an areaStyle", () => {
  const opt = buildOption({ chartType: "area", categoryField: "region" }, wide);
  expect(series(opt)[0].type).toBe("line");
  expect(series(opt)[0].areaStyle).toBeDefined();
});

test("pie/doughnut build a single pie series", () => {
  const pie = buildOption({ chartType: "pie", categoryField: "region", valueField: "2025" }, wide);
  expect(series(pie)).toHaveLength(1);
  expect(series(pie)[0].type).toBe("pie");
  const doughnut = buildOption({ chartType: "doughnut", categoryField: "region", valueField: "2025" }, wide);
  expect(Array.isArray(series(doughnut)[0].radius)).toBe(true);
});

test("axis types are configurable (time / log)", () => {
  const opt = buildOption({ chartType: "line", categoryField: "region", xAxisType: "time", yAxisType: "log" }, wide);
  expect((opt as { xAxis?: { type?: string } }).xAxis?.type).toBe("time");
  expect((opt as { yAxis?: { type?: string } }).yAxis?.type).toBe("log");
});

test("tooltip and legend are on by default; zoom adds dataZoom", () => {
  const base = buildOption({ chartType: "bar", categoryField: "region" }, wide);
  expect((base as { tooltip?: unknown }).tooltip).toBeDefined();
  expect((base as { legend?: unknown }).legend).toBeDefined();
  expect((base as { dataZoom?: unknown }).dataZoom).toBeUndefined();
  const zoomed = buildOption({ chartType: "bar", categoryField: "region", zoom: true }, wide);
  expect((zoomed as { dataZoom?: unknown }).dataZoom).toBeDefined();
});

test("advanced option JSON deep-merges over the built option", () => {
  const opt = buildOption(
    { chartType: "bar", categoryField: "region", title: "Base", advancedOption: JSON.stringify({ backgroundColor: "#000", title: { text: "Override" } }) },
    wide,
  );
  expect((opt as { backgroundColor?: string }).backgroundColor).toBe("#000");
  expect((opt as { title?: { text?: string } }).title?.text).toBe("Override");
  // untouched built keys survive the merge
  expect(series(opt)).toHaveLength(2);
});

test("invalid advanced JSON is ignored, not thrown", () => {
  const opt = buildOption({ chartType: "bar", categoryField: "region", advancedOption: "{ not json" }, wide);
  expect(series(opt)).toHaveLength(2);
});

test("heatmap encodes category × series into cells with a visualMap", () => {
  const opt = buildOption({ chartType: "heatmap", categoryField: "region" }, wide);
  expect(series(opt)[0].type).toBe("heatmap");
  expect((opt as { visualMap?: unknown }).visualMap).toBeDefined();
  // 2 categories × 2 series = 4 cells
  expect(series(opt)[0].data).toHaveLength(4);
});

test("gauge shows a single value", () => {
  const opt = buildOption({ chartType: "gauge", categoryField: "region", valueField: "2025" }, wide);
  expect(series(opt)[0].type).toBe("gauge");
  expect(series(opt)[0].data[0].value).toBe(10);
});

test("radar builds one radar series per column", () => {
  const opt = buildOption({ chartType: "radar", categoryField: "region" }, wide);
  expect(series(opt)[0].type).toBe("radar");
  expect(series(opt)[0].data).toHaveLength(2);
  expect((opt as { radar?: { indicator?: unknown[] } }).radar?.indicator).toHaveLength(2);
});

test("buildCompareOption renders two aligned series on a relative offset axis", () => {
  const current = [{ bucket: "2026-01-01 00:00:00", value: 10 }, { bucket: "2026-01-02 00:00:00", value: 12 }];
  const reference = [{ bucket: "2025-01-01 00:00:00", value: 8 }, { bucket: "2025-01-02 00:00:00", value: 9 }];
  const opt = buildCompareOption({ chartType: "line" }, current, reference, "day");
  expect(series(opt)).toHaveLength(2);
  expect(series(opt).map((s) => s.name)).toEqual(["Période courante", "Référence"]);
  expect(series(opt)[0].data).toEqual([10, 12]);
  expect(series(opt)[1].data).toEqual([8, 9]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Jour 1", "Jour 2"]);
  expect(series(opt)[1].lineStyle?.type).toBe("dashed");
});

test("buildCompareOption labels the offset axis by week/month depending on bucket", () => {
  const weekOpt = buildCompareOption({ chartType: "line" }, [{ bucket: "w", value: 1 }], [], "week");
  expect((weekOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Semaine 1"]);
  const monthOpt = buildCompareOption({ chartType: "area" }, [{ bucket: "m", value: 1 }], [], "month");
  expect((monthOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Mois 1"]);
});

test("buildCompareOption applies the yAxisUnit/yAxisFormat formatter like buildOption", () => {
  const opt = buildCompareOption({ chartType: "line", yAxisUnit: "kg" }, [{ bucket: "d", value: 1 }], [], "day");
  const formatter = (opt as { yAxis?: { axisLabel?: { formatter?: (v: unknown) => string } } }).yAxis?.axisLabel?.formatter;
  expect(formatter?.(5)).toBe("5 kg");
});

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

test("funnel uses an item tooltip trigger, not axis", () => {
  const funnelRows: DataRecord[] = [
    { id: "1", properties: { stage: "Visite", value: 100 } },
    { id: "2", properties: { stage: "Panier", value: 40 } },
  ];
  const opt = buildOption({ chartType: "funnel", categoryField: "stage", valueField: "value" }, funnelRows);
  expect((opt as { tooltip?: { trigger?: string } }).tooltip?.trigger).toBe("item");
});

test("histogram renders one bar series labeled by bucket bounds", () => {
  const opt = buildOption({ chartType: "histogram" }, histogramRows);
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("bar");
  expect(series(opt)[0].data).toEqual([3, 7]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["0–5", "10–15"]);
});

const flows: DataRecord[] = [
  { id: "1", properties: { origin: "Paris", destination: "Lyon", value: 10 } },
  { id: "2", properties: { origin: "Paris", destination: "Marseille", value: 5 } },
  { id: "3", properties: { origin: "Lyon", destination: "Marseille", value: 3 } }, // "Lyon" is both a destination and an origin
];

test("sankey builds nodes (tagged by role) and links from source/target/value encodings", () => {
  const opt = buildOption(
    { chartType: "sankey", encodings: { source: "origin", target: "destination", value: "value" } }, flows,
  );
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("sankey");
  expect(series(opt)[0].links).toEqual([
    { source: "Paris", target: "Lyon", value: 10 },
    { source: "Paris", target: "Marseille", value: 5 },
    { source: "Lyon", target: "Marseille", value: 3 },
  ]);
  const nodesByName = Object.fromEntries(series(opt)[0].data.map((n: { name: string; _role: string }) => [n.name, n._role]));
  expect(nodesByName.Paris).toBe("source");
  expect(nodesByName.Marseille).toBe("target");
  // Lyon is both a target (row 1) and a source (row 3) — source wins (documented tie-break).
  expect(nodesByName.Lyon).toBe("source");
});

const sales: DataRecord[] = [
  { id: "1", properties: { region: "Nord", city: "Lille", value: 10 } },
  { id: "2", properties: { region: "Nord", city: "Reims", value: 5 } },
  { id: "3", properties: { region: "Sud", city: "Nice", value: 7 } },
];

test("treemap builds a hierarchy from levels, summing values bottom-up", () => {
  const opt = buildOption(
    { chartType: "treemap", encodings: { levels: ["region", "city"], value: "value" } }, sales,
  );
  expect(series(opt)).toHaveLength(1);
  expect(series(opt)[0].type).toBe("treemap");
  const tree = series(opt)[0].data as { name: string; value: number; children?: { name: string; value: number }[] }[];
  const nord = tree.find((n) => n.name === "Nord")!;
  expect(nord.value).toBe(15);
  expect(nord.children).toEqual([{ name: "Lille", value: 10 }, { name: "Reims", value: 5 }]);
  const sud = tree.find((n) => n.name === "Sud")!;
  expect(sud.value).toBe(7);
});

test("sunburst uses the same hierarchy builder as treemap", () => {
  const opt = buildOption({ chartType: "sunburst", encodings: { levels: ["region"], value: "value" } }, sales);
  expect(series(opt)[0].type).toBe("sunburst");
  const tree = series(opt)[0].data as { name: string; value: number }[];
  expect(tree.find((n) => n.name === "Nord")?.value).toBe(15);
});

test("treemap groups missing intermediate-level values under a literal placeholder node", () => {
  const withGap: DataRecord[] = [
    { id: "1", properties: { region: "Nord", city: null, value: 4 } },
    { id: "2", properties: { region: "Nord", city: "Lille", value: 6 } },
  ];
  const opt = buildOption({ chartType: "treemap", encodings: { levels: ["region", "city"], value: "value" } }, withGap);
  const nord = (series(opt)[0].data as { name: string; children?: { name: string; value: number }[] }[]).find((n) => n.name === "Nord")!;
  expect(nord.children).toEqual(expect.arrayContaining([{ name: "—", value: 4 }, { name: "Lille", value: 6 }]));
});

test("resolveClickFilter: default types (bar/pie/...) resolve categoryField, like today", () => {
  expect(resolveClickFilter("bar", { categoryField: "region" }, { name: "Nord" })).toEqual({ field: "region", value: "Nord" });
  expect(resolveClickFilter("bar", {}, { name: "Nord" })).toBeNull(); // no categoryField → no filter, unchanged
});

test("resolveClickFilter: funnel resolves categoryField same as pie/bar", () => {
  expect(resolveClickFilter("funnel", { categoryField: "stage" }, { name: "Panier" })).toEqual({ field: "stage", value: "Panier" });
});

test("resolveClickFilter: histogram never resolves a filter", () => {
  expect(resolveClickFilter("histogram", { categoryField: "x" }, { name: "0–5" })).toBeNull();
});

test("resolveClickFilter: treemap/sunburst resolve the deepest clicked level", () => {
  const props = { chartType: "treemap", encodings: { levels: ["region", "city"] } };
  // Clicking a leaf: treePathInfo has 2 entries (region, city) → depth 1 → levels[1] = "city".
  expect(resolveClickFilter("treemap", props, { name: "Lille", treePathInfo: [{ name: "Nord" }, { name: "Lille" }] }))
    .toEqual({ field: "city", value: "Lille" });
  // Clicking a root: treePathInfo has 1 entry → depth 0 → levels[0] = "region".
  expect(resolveClickFilter("treemap", props, { name: "Nord", treePathInfo: [{ name: "Nord" }] }))
    .toEqual({ field: "region", value: "Nord" });
});

test("resolveClickFilter: sankey resolves source or target depending on the clicked node's role, ignores edge clicks", () => {
  const props = { chartType: "sankey", encodings: { source: "origin", target: "destination" } };
  expect(resolveClickFilter("sankey", props, { dataType: "node", name: "Paris", data: { _role: "source" } }))
    .toEqual({ field: "origin", value: "Paris" });
  expect(resolveClickFilter("sankey", props, { dataType: "node", name: "Lyon", data: { _role: "target" } }))
    .toEqual({ field: "destination", value: "Lyon" });
  expect(resolveClickFilter("sankey", props, { dataType: "edge", name: "Paris" })).toBeNull();
});
