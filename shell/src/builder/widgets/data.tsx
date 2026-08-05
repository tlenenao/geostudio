// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetFilter } from "../DataContext";
import { useSetCrossFilter } from "../AnalyticsContext";
import { evaluateExpression } from "../expr";
import type { DataRecord } from "../../api/types";
import { ExplorerMenu } from "./ExplorerMenu";

type CalculatedColumn = { label: string; expr: string };
type TableColumn = string | CalculatedColumn;

function isCalculatedColumn(c: TableColumn): c is CalculatedColumn {
  return typeof c === "object" && c !== null;
}

function firstField(records: DataRecord[]): string | undefined {
  return records[0] ? Object.keys(records[0].properties)[0] : undefined;
}

export function registerDataWidgets(): void {
  registerWidget({
    type: "list",
    label: "Liste",
    defaultProps: { dataSourceId: "", titleField: "" },
    defaultSize: { w: 4, h: 4 },
    events: ["itemSelected"],
    actions: ["setFilter"],
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Champ titre
          <input aria-label="Champ titre" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.titleField ?? "")} onChange={(e) => onChange({ ...props, titleField: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const setFilter = useSetFilter();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "setFilter", (payload) => {
        const dsId = String(props.dataSourceId ?? "");
        if (dsId) setFilter(dsId, (payload as Record<string, unknown>) ?? {});
      });
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const field = String(props.titleField || firstField(data.records) || "");

      function selectRecord(r: DataRecord) {
        ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r);
        const datasetId = ctx.data?.datasetId;
        const pkColumn = ctx.data?.pkColumn;
        if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(r.id), String(props.dataSourceId ?? ""), r.geometry);
      }

      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <ul className="flex flex-col gap-0.5 text-sm">
            {data.records.map((r) => (
              <li
                key={String(r.id)}
                className="cursor-pointer truncate border-b border-[var(--gs-color-border)] py-0.5 text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
                onClick={() => selectRecord(r)}
              >
                {String(r.properties[field] ?? r.id)}
              </li>
            ))}
          </ul>
        </div>
      );
    },
  });

  registerWidget({
    type: "table",
    label: "Table",
    defaultProps: { dataSourceId: "", columns: [], pageSize: 10 },
    defaultSize: { w: 6, h: 4 },
    events: ["itemSelected"],
    actions: ["setFilter"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const columns = (props.columns as TableColumn[] | undefined) ?? [];
      const plainColumns = columns.filter((c): c is string => typeof c === "string");
      const calculatedColumns = columns.filter(isCalculatedColumn);

      function setPlainColumns(next: string[]) {
        onChange({ ...props, columns: [...next, ...calculatedColumns] });
      }
      function addCalculatedColumn() {
        onChange({ ...props, columns: [...plainColumns, ...calculatedColumns, { label: "Nouvelle colonne", expr: "" }] });
      }
      function updateCalculatedColumn(index: number, patch: Partial<CalculatedColumn>) {
        const next = calculatedColumns.map((c, i) => (i === index ? { ...c, ...patch } : c));
        onChange({ ...props, columns: [...plainColumns, ...next] });
      }
      function removeCalculatedColumn(index: number) {
        onChange({ ...props, columns: [...plainColumns, ...calculatedColumns.filter((_, i) => i !== index)] });
      }

      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className="flex flex-col gap-1">Colonnes (séparées par des virgules)
            <input aria-label="Colonnes" className="h-9 rounded-md border border-slate-300 px-2"
              value={plainColumns.join(",")}
              onChange={(e) => setPlainColumns(e.target.value.split(",").map((c) => c.trim()).filter(Boolean))} />
          </label>
          {calculatedColumns.map((col, i) => (
            <div key={i} className="flex flex-col gap-1 rounded border border-slate-200 p-2">
              <label className="flex flex-col gap-1">Libellé
                <input aria-label={`Libellé de la colonne calculée ${i + 1}`} className="h-9 rounded-md border border-slate-300 px-2"
                  value={col.label} onChange={(e) => updateCalculatedColumn(i, { label: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">Expression
                <input aria-label={`Expression de la colonne calculée ${i + 1}`} className="h-9 rounded-md border border-slate-300 px-2 font-mono"
                  value={col.expr} onChange={(e) => updateCalculatedColumn(i, { expr: e.target.value })} />
              </label>
              <button type="button" className="self-start text-xs text-red-600 underline" onClick={() => removeCalculatedColumn(i)}>
                Supprimer la colonne
              </button>
            </div>
          ))}
          <button type="button" className="self-start rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
            onClick={addCalculatedColumn}>
            Ajouter une colonne calculée
          </button>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const setFilter = useSetFilter();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "setFilter", (payload) => {
        const dsId = String(props.dataSourceId ?? "");
        if (dsId) setFilter(dsId, (payload as Record<string, unknown>) ?? {});
      });
      const [sortCol, setSortCol] = useState<string | null>(null);
      const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
      const [page, setPage] = useState(0);
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const rawColumns = (props.columns as TableColumn[] | undefined) ?? [];
      const columns: TableColumn[] = rawColumns.length ? rawColumns : Object.keys(data.records[0]?.properties ?? {});

      function columnKey(c: TableColumn): string {
        return isCalculatedColumn(c) ? c.label : c;
      }
      function columnLabel(c: TableColumn): string {
        return isCalculatedColumn(c) ? c.label : c;
      }
      function cellValue(c: TableColumn, r: DataRecord): string {
        if (!isCalculatedColumn(c)) return String(r.properties[c] ?? "");
        const value = evaluateExpression(c.expr, { vars: ctx.variables ?? {}, record: r.properties, user: ctx.user ?? { name: "" } });
        return value === undefined || value === null ? "" : String(value);
      }

      const sorted = [...data.records];
      if (sortCol) {
        const dir = sortDir === "asc" ? 1 : -1;
        sorted.sort((a, b) => {
          const av = a.properties[sortCol];
          const bv = b.properties[sortCol];
          if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
          return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
        });
      }
      const pageSize = Number(props.pageSize) || 10;
      const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
      const current = Math.min(page, pageCount - 1);
      const shown = sorted.slice(current * pageSize, current * pageSize + pageSize);

      function toggleSort(c: string) {
        if (sortCol === c) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        else { setSortCol(c); setSortDir("asc"); }
        setPage(0);
      }

      function selectRecord(r: DataRecord) {
        ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r);
        const datasetId = ctx.data?.datasetId;
        const pkColumn = ctx.data?.pkColumn;
        if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(r.id), String(props.dataSourceId ?? ""), r.geometry);
      }

      return (
        <div className="relative flex h-full flex-col text-xs">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                {columns.map((c) => {
                  const key = columnKey(c);
                  return (
                    <th key={key} className="border-b border-[var(--gs-color-border)] p-1">
                      {isCalculatedColumn(c) ? (
                        <span className="font-medium">{columnLabel(c)}</span>
                      ) : (
                        <button type="button" className="flex items-center gap-1 font-medium" onClick={() => toggleSort(key)}>
                          {columnLabel(c)}{sortCol === key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className="cursor-pointer hover:bg-[var(--gs-color-surface)]"
                  onClick={() => selectRecord(r)}
                >
                  {columns.map((c) => <td key={columnKey(c)} className="border-b border-[var(--gs-color-border)] p-1">{cellValue(c, r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {pageCount > 1 && (
            <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-[var(--gs-color-muted)]">
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
              <span>Page {current + 1} / {pageCount}</span>
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
            </div>
          )}
        </div>
      );
    },
  });
}
