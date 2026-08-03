// SPDX-License-Identifier: Apache-2.0
import type { DataRecord } from "../../api/types";

export type PivotGrid = {
  rowValues: string[];
  colValues: string[];
  measures: string[];
  cell(row: string, col: string, measure: string): number;
  rowTotal(row: string, measure: string): number;
  colTotal(col: string, measure: string): number;
  grandTotal(measure: string): number;
};

const EMPTY_LABEL = "—";
const KEY_SEP = "::";

function normalizeLabel(value: unknown): string {
  if (value === null || value === undefined || value === "") return EMPTY_LABEL;
  return String(value);
}

function cellKey(row: string, col: string, measure: string): string {
  return `${row}${KEY_SEP}${col}${KEY_SEP}${measure}`;
}

// Reshapes the tidy rows already returned by a `groupBy: [rowsField,
// colsField]` + `measures` statistics DataSource (core, SP-14f, unchanged)
// into a 2D crosstab, entirely client-side — see SP-14g design §2-3 for why
// no core change is needed.
export function buildPivotGrid(records: DataRecord[], rowsField: string, colsField: string): PivotGrid | null {
  if (!rowsField || !colsField || records.length === 0) return null;
  const first = records[0].properties;
  if (!(rowsField in first) || !(colsField in first)) return null;
  const measures = Object.keys(first).filter((k) => k !== rowsField && k !== colsField);
  if (measures.length === 0) return null;

  const rowSet = new Set<string>();
  const colSet = new Set<string>();
  const values = new Map<string, number>();

  for (const record of records) {
    const rowVal = normalizeLabel(record.properties[rowsField]);
    const colVal = normalizeLabel(record.properties[colsField]);
    rowSet.add(rowVal);
    colSet.add(colVal);
    for (const measure of measures) {
      const raw = Number(record.properties[measure] ?? 0);
      const value = Number.isFinite(raw) ? raw : 0;
      const key = cellKey(rowVal, colVal, measure);
      values.set(key, (values.get(key) ?? 0) + value);
    }
  }

  const rowValues = [...rowSet].sort((a, b) => a.localeCompare(b));
  const colValues = [...colSet].sort((a, b) => a.localeCompare(b));

  function cell(row: string, col: string, measure: string): number {
    return values.get(cellKey(row, col, measure)) ?? 0;
  }
  function rowTotal(row: string, measure: string): number {
    return colValues.reduce((sum, col) => sum + cell(row, col, measure), 0);
  }
  function colTotal(col: string, measure: string): number {
    return rowValues.reduce((sum, row) => sum + cell(row, col, measure), 0);
  }
  function grandTotal(measure: string): number {
    return rowValues.reduce((sum, row) => sum + rowTotal(row, measure), 0);
  }

  return { rowValues, colValues, measures, cell, rowTotal, colTotal, grandTotal };
}
