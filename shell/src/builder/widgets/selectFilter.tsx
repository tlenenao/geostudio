// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useAnalyticsContext, useClearCrossFilter, useSetCrossFilter } from "../AnalyticsContext";

type SelectOption = { value: string; count: number };

export function registerSelectFilterWidget(): void {
  registerWidget({
    type: "selectFilter",
    label: "Sélecteur",
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
      { name: "field", type: "string", label: "Champ", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "Filtrer" },
    ],
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect
          value={String(props.dataSourceId ?? "")}
          dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })}
        />
        <label className="flex flex-col gap-1">
          Champ
          <input
            aria-label="Champ du sélecteur"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")}
            onChange={(e) => onChange({ ...props, field: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Libellé
          <input
            aria-label="Libellé du sélecteur"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const analyticsCtx = useAnalyticsContext();
      const setCrossFilter = useSetCrossFilter();
      const clearCrossFilter = useClearCrossFilter();
      const datasetId = ctx.data?.datasetId;
      const field = String(props.field ?? "");
      const originSourceId = String(props.dataSourceId ?? "");

      const query = useQuery({
        queryKey: ["analytics-filter-options", datasetId, field],
        queryFn: async () => {
          const rows = await client.queryDataSource({
            id: `analytics-filter-${datasetId}-${field}`,
            type: "statistics",
            service: "core",
            layer: "",
            datasetId,
            query: { groupBy: field },
          });
          return rows.map((r): SelectOption => ({
            value: String(r.id),
            count: Number(r.properties.value ?? 0),
          }));
        },
        enabled: Boolean(datasetId && field),
      });

      if (!datasetId || !field) {
        return (
          <p className="text-xs text-[var(--gs-color-muted)]">
            Liez ce filtre à une source dataset et un champ
          </p>
        );
      }
      if (query.isLoading)
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (query.isError || !query.data) {
        return (
          <p role="alert" className="text-xs text-[var(--gs-color-muted)]">
            Impossible de charger les valeurs
          </p>
        );
      }

      const active = analyticsCtx.crossFilter[datasetId];
      const checked =
        active && active.field === field && Array.isArray(active.value) ? active.value : [];

      function toggle(value: string, isChecked: boolean) {
        const next = isChecked ? [...checked, value] : checked.filter((v) => v !== value);
        if (next.length === 0) clearCrossFilter(datasetId!);
        else setCrossFilter(datasetId!, field, next, originSourceId);
      }

      return (
        <fieldset className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <legend>{String(props.label ?? "Filtrer")}</legend>
          {query.data.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={opt.value}
                checked={checked.includes(opt.value)}
                onChange={(e) => toggle(opt.value, e.target.checked)}
              />
              {opt.value} ({opt.count})
            </label>
          ))}
        </fieldset>
      );
    },
  });
}
