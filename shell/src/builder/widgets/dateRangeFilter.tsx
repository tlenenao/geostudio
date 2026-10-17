// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { registerWidget } from "../registry";
import { useAnalyticsContext, useSetTimeRange } from "../AnalyticsContext";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

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
        {t("widgetDateRangeFilter.labelAria")}
        <input
          className="h-9 rounded-md border border-rule px-2"
          value={String(props.label ?? "")}
          onChange={(e) => onChange({ ...props, label: e.target.value })}
        />
      </label>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      // AUD-059 : valeur dérivée du contexte (bookmark, ?ctx=) — jamais un état local qui
      // s'afficherait vide alors que le filtre est actif ; une plage inversée est refusée.
      const range = useAnalyticsContext().timeRange;
      const from = range?.from ?? "";
      const to = range?.to ?? "";
      const [draft, setDraft] = useState<{ from: string; to: string } | null>(null);
      const shownFrom = draft?.from ?? from;
      const shownTo = draft?.to ?? to;

      // Le contexte reprend la main quand il change (bookmark, ?ctx=, autre widget).
      useEffect(() => setDraft(null), [from, to]);

      function update(nextFrom: string, nextTo: string) {
        if (nextFrom && nextTo && nextFrom > nextTo) return;
        setDraft({ from: nextFrom, to: nextTo });
        if (nextFrom && nextTo) setTimeRange({ from: nextFrom, to: nextTo });
        else if (!nextFrom && !nextTo) setTimeRange(null);
        // une seule borne saisie : la plage appliquée reste en place jusqu'à la saisie complète
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? t("widgetDateRangeFilter.periodDefault"))}</span>
          <div className="flex gap-2">
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.startDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={shownFrom}
              onChange={(e) => update(e.target.value, shownTo)}
            />
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.endDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={shownTo}
              onChange={(e) => update(shownFrom, e.target.value)}
            />
          </div>
        </div>
      );
    },
  });
}
