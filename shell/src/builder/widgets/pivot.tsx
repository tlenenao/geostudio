// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useSetCrossFilter } from "../AnalyticsContext";
import { buildPivotGrid } from "./pivotTable";
import { ExplorerMenu } from "./ExplorerMenu";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";
const thCls = "border-b border-[var(--gs-color-border)] p-1";

type PivotEncodings = { rows?: string; columns?: string };

export function registerPivotWidget(): void {
  registerWidget({
    type: "pivot",
    // Not "Tableau croisé": that label starts with "Table", and every E2E
    // scenario in this file locates the existing Table widget's palette
    // button via `getByRole("button", { name: "Table" })` — Playwright's
    // name matching is substring-based by default, so "Table" would start
    // matching this button too (strict-mode violation) across the whole
    // existing suite. "Pivot" collides with no existing widget label.
    label: "Pivot",
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => {
      const encodings = (props.encodings as PivotEncodings | undefined) ?? {};
      const setEncodings = (patch: PivotEncodings) => onChange({ ...props, encodings: { ...encodings, ...patch } });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className={labelCls}>Champ lignes
            <input aria-label="Champ lignes" className={inputCls}
              value={String(encodings.rows ?? "")} onChange={(e) => setEncodings({ rows: e.target.value })} />
          </label>
          <label className={labelCls}>Champ colonnes
            <input aria-label="Champ colonnes" className={inputCls}
              value={String(encodings.columns ?? "")} onChange={(e) => setEncodings({ columns: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du tableau croisé" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => onChange({ ...props, title: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const setCrossFilter = useSetCrossFilter();
      const data = ctx.data;
      const encodings = (props.encodings as PivotEncodings | undefined) ?? {};
      const rowsField = String(encodings.rows ?? "");
      const colsField = String(encodings.columns ?? "");
      const dataSourceId = String(props.dataSourceId ?? "");

      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;

      const grid = buildPivotGrid(data.records, rowsField, colsField);
      if (!grid) return <p className="text-xs text-[var(--gs-color-muted)]">Configurez les champs lignes et colonnes</p>;

      function clickRow(rowValue: string) {
        if (data?.datasetId) setCrossFilter(data.datasetId, rowsField, rowValue, dataSourceId);
      }
      function clickCol(colValue: string) {
        if (data?.datasetId) setCrossFilter(data.datasetId, colsField, colValue, dataSourceId);
      }

      const showMeasureRow = grid.measures.length > 1;

      return (
        <div className="relative h-full overflow-auto text-xs">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={dataSourceId} />
          {props.title ? <p className="mb-1 font-medium">{String(props.title)}</p> : null}
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                <th className={thCls} />
                {grid.colValues.map((col) => (
                  <th key={col} colSpan={grid.measures.length} className={thCls}>
                    <button type="button" className="font-medium" onClick={() => clickCol(col)}>{col}</button>
                  </th>
                ))}
                <th colSpan={grid.measures.length} className={`${thCls} font-medium`}>Total</th>
              </tr>
              {showMeasureRow && (
                <tr>
                  <th className={thCls} />
                  {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                    <th key={`${col}-${m}`} className={`${thCls} font-normal text-[var(--gs-color-muted)]`}>{m}</th>
                  )))}
                  {grid.measures.map((m) => (
                    <th key={`total-${m}`} className={`${thCls} font-normal text-[var(--gs-color-muted)]`}>{m}</th>
                  ))}
                </tr>
              )}
            </thead>
            <tbody>
              {grid.rowValues.map((row) => (
                <tr key={row}>
                  <th scope="row" className={`${thCls} text-left font-medium`}>
                    <button type="button" onClick={() => clickRow(row)}>{row}</button>
                  </th>
                  {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                    <td key={`${col}-${m}`} className={thCls}>{grid.cell(row, col, m)}</td>
                  )))}
                  {grid.measures.map((m) => (
                    <td key={`total-${m}`} className={`${thCls} font-medium`}>{grid.rowTotal(row, m)}</td>
                  ))}
                </tr>
              ))}
              <tr>
                <th scope="row" className="p-1 text-left font-medium">Total</th>
                {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                  <td key={`total-${col}-${m}`} className="p-1 font-medium">{grid.colTotal(col, m)}</td>
                )))}
                {grid.measures.map((m) => (
                  <td key={`grand-${m}`} className="p-1 font-medium">{grid.grandTotal(m)}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      );
    },
  });
}
