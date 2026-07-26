// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useClearCrossFilter, useSetCrossFilter } from "../AnalyticsContext";

type Bounds = { min: number; max: number };

export function registerSliderFilterWidget(): void {
  registerWidget({
    type: "sliderFilter",
    label: "Curseur",
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Champ
          <input aria-label="Champ du curseur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé du curseur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const setCrossFilter = useSetCrossFilter();
      const clearCrossFilter = useClearCrossFilter();
      const datasetId = ctx.data?.datasetId;
      const field = String(props.field ?? "");
      const originSourceId = String(props.dataSourceId ?? "");

      const query = useQuery({
        queryKey: ["analytics-filter-bounds", datasetId, field],
        queryFn: async (): Promise<Bounds> => {
          const rows = await client.queryDataSource({
            id: `analytics-filter-${datasetId}-${field}`, type: "statistics", service: "core",
            layer: "", datasetId,
            query: { measures: [{ field, agg: "min", label: "min" }, { field, agg: "max", label: "max" }] },
          });
          const properties = rows[0]?.properties ?? {};
          return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
        },
        enabled: Boolean(datasetId && field),
      });

      const [from, setFrom] = useState<number | null>(null);
      const [to, setTo] = useState<number | null>(null);
      useEffect(() => {
        if (query.data) { setFrom(query.data.min); setTo(query.data.max); }
      }, [query.data]);

      if (!datasetId || !field) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Liez ce filtre à une source dataset et un champ</p>;
      }
      if (query.isLoading || !query.data || from === null || to === null) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      }
      if (query.isError) return <p role="alert" className="text-xs text-[var(--gs-color-muted)]">Impossible de charger les bornes</p>;

      const { min, max } = query.data;

      function commit(nextFrom: number, nextTo: number) {
        setFrom(nextFrom);
        setTo(nextTo);
        if (nextFrom === min && nextTo === max) clearCrossFilter(datasetId!);
        else setCrossFilter(datasetId!, field, { from: String(nextFrom), to: String(nextTo) }, originSourceId);
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? "Filtrer")} ({from} – {to})</span>
          <div className="flex gap-2">
            <input type="range" aria-label="Borne minimale" min={min} max={max} value={from}
              onChange={(e) => commit(Math.min(Number(e.target.value), to), to)} />
            <input type="range" aria-label="Borne maximale" min={min} max={max} value={to}
              onChange={(e) => commit(from, Math.max(Number(e.target.value), from))} />
          </div>
        </div>
      );
    },
  });
}
