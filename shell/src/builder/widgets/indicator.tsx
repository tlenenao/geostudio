// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";

export function registerIndicatorWidget(): void {
  registerWidget({
    type: "indicator",
    label: "Indicateur",
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé de l'indicateur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Agrégation
          <select aria-label="Agrégation" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.agg ?? "count")} onChange={(e) => onChange({ ...props, agg: e.target.value })}>
            <option value="count">Nombre</option>
            <option value="sum">Somme</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">Champ (pour la somme)
          <input aria-label="Champ agrégé" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;
      const agg = String(props.agg ?? "count");
      const field = String(props.field ?? "");
      const value =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      return (
        <div className="flex h-full flex-col items-center justify-center">
          <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
        </div>
      );
    },
  });
}
