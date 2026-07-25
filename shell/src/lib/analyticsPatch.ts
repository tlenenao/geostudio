// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";

// Pure translation of the global analytics context into query-filter keys
// for one DataSource, mirroring the __gte/__lte/__in suffixes the core
// understands (features/repository.py, analytics/aggregate.py). `datasets`
// keys are DatasetConfig objects already resolved by the caller (DataContext)
// — this function never fetches.
export function derivePatch(
  source: DataSource,
  ctx: AnalyticsContextState,
  datasets: Record<string, DatasetConfig>,
): Record<string, unknown> {
  if (!source.datasetId) return {};
  const dataset = datasets[source.datasetId];
  if (!dataset) return {};

  const patch: Record<string, unknown> = {};

  if (ctx.timeRange && dataset.timeField) {
    patch[`${dataset.timeField}__gte`] = ctx.timeRange.from;
    patch[`${dataset.timeField}__lte`] = ctx.timeRange.to;
  }

  if (ctx.extent && dataset.reactsToExtent) {
    patch.bbox = ctx.extent.join(",");
  }

  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    else patch[crossFilter.field] = crossFilter.value;
  }

  return patch;
}
