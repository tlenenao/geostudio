// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState, CrossFilterValue } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { bboxFromGeometry } from "./geometryBbox";

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

  const directCrossFilter = ctx.crossFilter[source.datasetId];
  if (directCrossFilter && directCrossFilter.originSourceId !== source.id) {
    applyCrossFilterValue(patch, directCrossFilter.field, directCrossFilter.value);
  }

  // SP-14n — cross-filter inter-datasets : pour chaque AUTRE dataset avec un
  // cross-filter actif, vérifier s'il déclare un lien vers le dataset de
  // cette source, et traduire en conséquence. Un seul saut (pas de chaînage
  // transitif) ; en cas de liens contradictoires vers la même cible, le
  // dernier résolu gagne (limite documentée, spec §1).
  for (const [originDatasetId, entry] of Object.entries(ctx.crossFilter)) {
    if (!entry || originDatasetId === source.datasetId) continue;
    const originDataset = datasets[originDatasetId];
    const link = originDataset?.crossFilterLinks?.find((l) => l.targetDatasetId === source.datasetId);
    if (!link) continue;
    if (link.mode === "attribute") {
      if (entry.field === link.sourceField) applyCrossFilterValue(patch, link.targetField, entry.value);
    } else if (entry.geometry !== undefined) {
      if (link.precision === "bbox") {
        const bbox = bboxFromGeometry(entry.geometry);
        if (bbox) patch.bbox = bbox.join(",");
      } else {
        patch.geomIntersects = entry.geometry;
      }
    }
  }

  return patch;
}

function applyCrossFilterValue(patch: Record<string, unknown>, field: string, value: CrossFilterValue): void {
  if (Array.isArray(value)) {
    patch[`${field}__in`] = value.join(",");
  } else if (typeof value === "object") {
    patch[`${field}__gte`] = value.from;
    patch[`${field}__lte`] = value.to;
  } else {
    patch[field] = value;
  }
}
