// SPDX-License-Identifier: Apache-2.0
import { useAnalyticsContext, useClearCrossFilter, useSetExtent, useSetTimeRange, type CrossFilterValue } from "./AnalyticsContext";

const chipCls = "flex items-center gap-1 rounded-full border border-[var(--gs-color-border)] px-2 py-1";

function formatCrossFilterValue(value: CrossFilterValue): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return `${value.from} → ${value.to}`;
  return value;
}

export function AnalyticsContextIndicator(): JSX.Element | null {
  const ctx = useAnalyticsContext();
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
          Période : {ctx.timeRange.from} → {ctx.timeRange.to}
          <button type="button" aria-label="Effacer la période" onClick={() => setTimeRange(null)}>×</button>
        </span>
      )}
      {ctx.extent && (
        <span className={chipCls}>
          Emprise carte active
          <button type="button" aria-label="Effacer l'emprise" onClick={() => setExtent(null)}>×</button>
        </span>
      )}
      {crossFilterIds.map((datasetId) => {
        const entry = ctx.crossFilter[datasetId]!;
        return (
          <span key={datasetId} className={chipCls}>
            {entry.field} : {formatCrossFilterValue(entry.value)}
            <button type="button" aria-label={`Effacer le filtre ${entry.field}`} onClick={() => clearCrossFilter(datasetId)}>×</button>
          </span>
        );
      })}
      {chipCount >= 2 && (
        <button type="button" className="ml-auto underline" onClick={clearAll}>Tout effacer</button>
      )}
    </div>
  );
}
