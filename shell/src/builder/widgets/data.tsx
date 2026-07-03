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
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
      const field = String(props.titleField || firstField(data.records) || "");
      return (
        <ul className="flex flex-col gap-0.5 text-sm">
          {data.records.map((r) => (
            <li
              key={String(r.id)}
              className="cursor-pointer truncate border-b border-slate-100 py-0.5 hover:bg-slate-50"
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
    defaultProps: { dataSourceId: "", columns: [] },
    defaultSize: { w: 6, h: 4 },
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
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
      const columns = ((props.columns as string[] | undefined)?.length
        ? (props.columns as string[])
        : Object.keys(data.records[0]?.properties ?? {}));
      return (
        <table className="w-full text-left text-xs">
          <thead>
            <tr>{columns.map((c) => <th key={c} className="border-b p-1">{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.records.map((r) => (
              <tr key={String(r.id)}>
                {columns.map((c) => <td key={c} className="border-b border-slate-100 p-1">{String(r.properties[c] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      );
    },
  });
}
