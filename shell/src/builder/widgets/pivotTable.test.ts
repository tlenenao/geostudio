// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { buildPivotGrid } from "./pivotTable";
import type { DataRecord } from "../../api/types";

const oneMeasure: DataRecord[] = [
  { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10 } },
  { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 5 } },
  { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 3 } },
  // "Sud"/"Q2" is deliberately absent — exercises the missing-combination fill.
];

test("builds a grid with cells, row totals, column totals and a grand total", () => {
  const grid = buildPivotGrid(oneMeasure, "region", "quarter");
  expect(grid).not.toBeNull();
  expect(grid!.rowValues).toEqual(["Nord", "Sud"]);
  expect(grid!.colValues).toEqual(["Q1", "Q2"]);
  expect(grid!.measures).toEqual(["sum_amount"]);
  expect(grid!.cell("Nord", "Q1", "sum_amount")).toBe(10);
  expect(grid!.cell("Nord", "Q2", "sum_amount")).toBe(5);
  expect(grid!.cell("Sud", "Q1", "sum_amount")).toBe(3);
  expect(grid!.rowTotal("Nord", "sum_amount")).toBe(15);
  expect(grid!.rowTotal("Sud", "sum_amount")).toBe(3);
  expect(grid!.colTotal("Q1", "sum_amount")).toBe(13);
  expect(grid!.colTotal("Q2", "sum_amount")).toBe(5);
  expect(grid!.grandTotal("sum_amount")).toBe(18);
});

test("a missing row×column combination reads as 0 in the cell", () => {
  const grid = buildPivotGrid(oneMeasure, "region", "quarter")!;
  expect(grid.cell("Sud", "Q2", "sum_amount")).toBe(0);
});

test("supports multiple measures, preserving the first record's property order", () => {
  const records: DataRecord[] = [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10, avg_amount: 5 } },
    { id: "2", properties: { region: "Sud", quarter: "Q1", sum_amount: 4, avg_amount: 2 } },
  ];
  const grid = buildPivotGrid(records, "region", "quarter")!;
  expect(grid.measures).toEqual(["sum_amount", "avg_amount"]);
  expect(grid.cell("Nord", "Q1", "avg_amount")).toBe(5);
  expect(grid.rowTotal("Nord", "avg_amount")).toBe(5);
});

test("returns null when rowsField or colsField is empty", () => {
  expect(buildPivotGrid(oneMeasure, "", "quarter")).toBeNull();
  expect(buildPivotGrid(oneMeasure, "region", "")).toBeNull();
});

test("returns null when records do not carry the configured fields", () => {
  const records: DataRecord[] = [{ id: "1", properties: { other: 1 } }];
  expect(buildPivotGrid(records, "region", "quarter")).toBeNull();
});

test("returns null when no measure column remains after excluding rows/columns fields", () => {
  const records: DataRecord[] = [{ id: "1", properties: { region: "Nord", quarter: "Q1" } }];
  expect(buildPivotGrid(records, "region", "quarter")).toBeNull();
});

test("returns null for an empty records array", () => {
  expect(buildPivotGrid([], "region", "quarter")).toBeNull();
});

test("normalizes null/undefined/empty-string row values to the same placeholder label", () => {
  const records: DataRecord[] = [
    { id: "1", properties: { region: null, quarter: "Q1", sum_amount: 1 } },
    { id: "2", properties: { region: undefined, quarter: "Q1", sum_amount: 2 } },
  ];
  const grid = buildPivotGrid(records, "region", "quarter")!;
  expect(grid.rowValues).toEqual(["—"]);
  expect(grid.cell("—", "Q1", "sum_amount")).toBe(3);
});
