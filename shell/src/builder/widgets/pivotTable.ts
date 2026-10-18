// SPDX-License-Identifier: Apache-2.0
import type { DataRecord } from "../../api/types";

export type PivotGrid = {
  rowValues: string[];
  colValues: string[];
  measures: string[];
  // AUD-059 : `null` = cellule absente (jamais un 0 inventé) ou total non additif (« — »).
  cell(row: string, col: string, measure: string): number | null;
  rowTotal(row: string, measure: string): number | null;
  colTotal(col: string, measure: string): number | null;
  grandTotal(measure: string): number | null;
};

// Le cœur nomme la colonne d'une mesure `<agg>_<champ>` (ou `<agg>`). Un total de moyennes,
// médianes, centiles, écarts-types ou distincts n'est pas la somme des cellules : on le masque.
// min/max se recomposent exactement ; le reste (libellé libre) reste additif comme avant.
const NON_ADDITIVE = /^(avg|median|percentile[\d.]*|stddev|countDistinct)(_|$)/;
const MIN = /^min(_|$)/;
const MAX = /^max(_|$)/;

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
export function buildPivotGrid(
  records: DataRecord[],
  rowsField: string,
  colsField: string,
): PivotGrid | null {
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
      const rawValue = record.properties[measure];
      if (rawValue === null || rawValue === undefined) continue;
      const raw = Number(rawValue);
      if (!Number.isFinite(raw)) continue;
      const key = cellKey(rowVal, colVal, measure);
      values.set(key, (values.get(key) ?? 0) + raw);
    }
  }

  const rowValues = [...rowSet].sort((a, b) => a.localeCompare(b));
  const colValues = [...colSet].sort((a, b) => a.localeCompare(b));

  function cell(row: string, col: string, measure: string): number | null {
    return values.get(cellKey(row, col, measure)) ?? null;
  }
  function combine(measure: string, cells: (number | null)[]): number | null {
    if (NON_ADDITIVE.test(measure)) return null;
    const present = cells.filter((c): c is number => c !== null);
    if (present.length === 0) return null;
    if (MIN.test(measure)) return Math.min(...present);
    if (MAX.test(measure)) return Math.max(...present);
    return present.reduce((sum, c) => sum + c, 0);
  }
  function rowTotal(row: string, measure: string): number | null {
    return combine(
      measure,
      colValues.map((col) => cell(row, col, measure)),
    );
  }
  function colTotal(col: string, measure: string): number | null {
    return combine(
      measure,
      rowValues.map((row) => cell(row, col, measure)),
    );
  }
  function grandTotal(measure: string): number | null {
    return combine(
      measure,
      rowValues.map((row) => rowTotal(row, measure)),
    );
  }

  return { rowValues, colValues, measures, cell, rowTotal, colTotal, grandTotal };
}
