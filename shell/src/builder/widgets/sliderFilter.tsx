// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useAnalyticsContext, useClearCrossFilter, useSetCrossFilter } from "../AnalyticsContext";
import { t } from "../../i18n";

type Bounds = { min: number; max: number };

export function registerSliderFilterWidget(): void {
  registerWidget({
    type: "sliderFilter",
    label: t("widgetSliderFilter.paletteLabel"),
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      {
        name: "dataSourceId",
        type: "dataSource",
        label: t("widgetSliderFilter.dataSourceConfig"),
        default: "",
      },
      { name: "field", type: "string", label: t("widgetSliderFilter.fieldConfig"), default: "" },
      {
        name: "label",
        type: "string",
        label: t("widgetSliderFilter.labelConfig"),
        default: "Filtrer",
      },
    ],
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect
          value={String(props.dataSourceId ?? "")}
          dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })}
        />
        <label className="flex flex-col gap-1">
          {t("widgetSliderFilter.fieldConfig")}
          <input
            aria-label={t("widgetSliderFilter.fieldAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")}
            onChange={(e) => onChange({ ...props, field: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetSliderFilter.labelConfig")}
          <input
            aria-label={t("widgetSliderFilter.labelAria")}
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
        queryKey: ["analytics-filter-bounds", datasetId, field],
        queryFn: async (): Promise<Bounds> => {
          const rows = await client.queryDataSource({
            id: `analytics-filter-${datasetId}-${field}`,
            type: "statistics",
            service: "core",
            layer: "",
            datasetId,
            query: {
              measures: [
                { field, agg: "min", label: "min" },
                { field, agg: "max", label: "max" },
              ],
            },
          });
          const properties = rows[0]?.properties ?? {};
          return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
        },
        enabled: Boolean(datasetId && field),
      });

      if (!datasetId || !field) {
        return (
          <p className="text-xs text-[var(--gs-color-muted)]">{t("widgetSliderFilter.unbound")}</p>
        );
      }
      if (query.isLoading)
        return <p className="text-xs text-[var(--gs-color-muted)]">{t("common.loading")}</p>;
      if (query.isError || !query.data) {
        return (
          <p role="alert" className="text-xs text-[var(--gs-color-muted)]">
            {t("widgetSliderFilter.loadBoundsError")}
          </p>
        );
      }

      const { min, max } = query.data;
      const active = analyticsCtx.crossFilter[datasetId];
      const activeRange =
        active &&
        active.field === field &&
        typeof active.value === "object" &&
        !Array.isArray(active.value)
          ? (active.value as { from: string; to: string })
          : null;
      const from = activeRange ? Number(activeRange.from) : min;
      const to = activeRange ? Number(activeRange.to) : max;

      function commit(nextFrom: number, nextTo: number) {
        if (nextFrom === min && nextTo === max) clearCrossFilter(datasetId!);
        else
          setCrossFilter(
            datasetId!,
            field,
            { from: String(nextFrom), to: String(nextTo) },
            originSourceId,
          );
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>
            {String(props.label ?? "Filtrer")} ({from} – {to})
          </span>
          <div className="flex gap-2">
            <input
              type="range"
              aria-label={t("widgetSliderFilter.minAria")}
              min={min}
              max={max}
              value={from}
              onChange={(e) => commit(Math.min(Number(e.target.value), to), to)}
            />
            <input
              type="range"
              aria-label={t("widgetSliderFilter.maxAria")}
              min={min}
              max={max}
              value={to}
              onChange={(e) => commit(from, Math.max(Number(e.target.value), from))}
            />
          </div>
        </div>
      );
    },
  });
}
