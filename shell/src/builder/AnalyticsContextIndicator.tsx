// SPDX-License-Identifier: Apache-2.0
import {
  useAnalyticsContext,
  useClearCrossFilter,
  useSetExtent,
  useSetTimeRange,
  type CrossFilterValue,
} from "./AnalyticsContext";
import { useDatasets } from "./DataContext";
import { t } from "../i18n";

const chipCls =
  "flex items-center gap-1 rounded-full border border-[var(--gs-color-border)] px-2 py-1";

function formatCrossFilterValue(value: CrossFilterValue): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return `${value.from} → ${value.to}`;
  return value;
}

export function AnalyticsContextIndicator() {
  const ctx = useAnalyticsContext();
  const datasets = useDatasets();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const clearCrossFilter = useClearCrossFilter();

  const crossFilterIds = Object.keys(ctx.crossFilter).filter((id) => ctx.crossFilter[id]);
  const chipCount = (ctx.timeRange ? 1 : 0) + (ctx.extent ? 1 : 0) + crossFilterIds.length;
  if (chipCount === 0) return null;

  function clearAll() {
    setTimeRange(null);
    setExtent(null);
    crossFilterIds.forEach((id) => clearCrossFilter(id));
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] p-2 text-xs text-[var(--gs-color-text)]">
      {ctx.timeRange && (
        <span className={chipCls}>
          {t("analyticsContext.periodLabel", { from: ctx.timeRange.from, to: ctx.timeRange.to })}
          <button
            type="button"
            aria-label={t("analyticsContext.clearPeriodAria")}
            onClick={() => setTimeRange(null)}
          >
            ×
          </button>
        </span>
      )}
      {ctx.extent && (
        <span className={chipCls}>
          {t("analyticsContext.extentActive")}
          <button
            type="button"
            aria-label={t("analyticsContext.clearExtentAria")}
            onClick={() => setExtent(null)}
          >
            ×
          </button>
        </span>
      )}
      {crossFilterIds.map((datasetId) => {
        const entry = ctx.crossFilter[datasetId]!;
        const propagatesTo = (datasets[datasetId]?.crossFilterLinks ?? [])
          .filter((link) =>
            link.mode === "attribute"
              ? link.sourceField === entry.field
              : entry.geometry !== undefined,
          )
          .map((link) => link.targetDatasetId);
        return (
          <span key={datasetId} className={chipCls}>
            {entry.field} : {formatCrossFilterValue(entry.value)}
            {propagatesTo.length > 0 && (
              <span className="text-[var(--gs-color-muted)]"> → {propagatesTo.join(", ")}</span>
            )}
            <button
              type="button"
              aria-label={t("analyticsContext.clearCrossFilterAria", { field: entry.field })}
              onClick={() => clearCrossFilter(datasetId)}
            >
              ×
            </button>
          </span>
        );
      })}
      {chipCount >= 2 && (
        <button type="button" className="ml-auto underline" onClick={clearAll}>
          {t("analyticsContext.clearAllButton")}
        </button>
      )}
    </div>
  );
}
