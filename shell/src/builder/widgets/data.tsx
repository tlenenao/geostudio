import { useState } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetFilter } from "../DataContext";
import type { DataRecord } from "../../api/types";

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
      useBusAction(ctx.bus, ctx.widgetId, "setFilter", (payload) => {
        const dsId = String(props.dataSourceId ?? "");
        if (dsId) setFilter(dsId, (payload as Record<string, unknown>) ?? {});
      });
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const field = String(props.titleField || firstField(data.records) || "");
      return (
        <ul className="flex flex-col gap-0.5 text-sm">
          {data.records.map((r) => (
            <li
              key={String(r.id)}
              className="cursor-pointer truncate border-b border-[var(--gs-color-border)] py-0.5 text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r)}
            >
              {String(r.properties[field] ?? r.id)}
            </li>
          ))}
        </ul>
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
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Colonnes (séparées par des virgules)
          <input aria-label="Colonnes" className="h-9 rounded-md border border-slate-300 px-2"
            value={(props.columns as string[] | undefined)?.join(",") ?? ""}
            onChange={(e) => onChange({ ...props, columns: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const setFilter = useSetFilter();
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
      const columns = ((props.columns as string[] | undefined)?.length
        ? (props.columns as string[])
        : Object.keys(data.records[0]?.properties ?? {}));

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

      return (
        <div className="flex h-full flex-col text-xs">
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b border-[var(--gs-color-border)] p-1">
                    <button type="button" className="flex items-center gap-1 font-medium" onClick={() => toggleSort(c)}>
                      {c}{sortCol === c ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className="cursor-pointer hover:bg-[var(--gs-color-surface)]"
                  onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", r)}
                >
                  {columns.map((c) => <td key={c} className="border-b border-[var(--gs-color-border)] p-1">{String(r.properties[c] ?? "")}</td>)}
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
