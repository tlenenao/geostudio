// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import { useSetTimeRange } from "../AnalyticsContext";
import { t } from "../../i18n";

export function registerDateRangeFilterWidget(): void {
  registerWidget({
    type: "dateRangeFilter",
    label: t("widgetDateRangeFilter.paletteLabel"),
    defaultProps: { label: t("widgetDateRangeFilter.periodDefault") },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      {
        name: "label",
        type: "string",
        label: t("widgetDateRangeFilter.labelConfig"),
        default: t("widgetDateRangeFilter.periodDefault"),
      },
    ],
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        {t("widgetDateRangeFilter.labelConfig")}
        <input
          aria-label={t("widgetDateRangeFilter.labelAria")}
          className="h-9 rounded-md border border-slate-300 px-2"
          value={String(props.label ?? "")}
          onChange={(e) => onChange({ ...props, label: e.target.value })}
        />
      </label>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [from, setFrom] = useState("");
      const [to, setTo] = useState("");

      function update(nextFrom: string, nextTo: string) {
        setFrom(nextFrom);
        setTo(nextTo);
        setTimeRange(nextFrom && nextTo ? { from: nextFrom, to: nextTo } : null);
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? t("widgetDateRangeFilter.periodDefault"))}</span>
          <div className="flex gap-2">
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.startDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={from}
              onChange={(e) => update(e.target.value, to)}
            />
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.endDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={to}
              onChange={(e) => update(from, e.target.value)}
            />
          </div>
        </div>
      );
    },
  });
}
