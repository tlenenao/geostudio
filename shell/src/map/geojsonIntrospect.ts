// SPDX-License-Identifier: Apache-2.0
import type { DataRecord } from "../api/types";
import type { SampleFieldFn, StatQueryFn } from "../builder/widgets/mapSymbology";

export async function fetchFeatureCollection(url: string): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Impossible de charger ${url} (HTTP ${res.status})`);
  const data: unknown = await res.json();
  if (
    typeof data !== "object" ||
    data === null ||
    (data as { type?: unknown }).type !== "FeatureCollection" ||
    !Array.isArray((data as { features?: unknown }).features)
  ) {
    throw new Error(`${url} n'est pas une FeatureCollection GeoJSON valide`);
  }
  return data as GeoJSON.FeatureCollection;
}

export function listFields(fc: GeoJSON.FeatureCollection): string[] {
  const fields = new Set<string>();
  for (const feature of fc.features) {
    for (const key of Object.keys(feature.properties ?? {})) fields.add(key);
  }
  return [...fields].sort();
}

function numericValues(fc: GeoJSON.FeatureCollection, field: string): number[] {
  const values: number[] = [];
  for (const feature of fc.features) {
    const raw = (feature.properties ?? {})[field];
    if (raw === null || raw === undefined) continue;
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isFinite(n)) values.push(n);
  }
  return values;
}

// Interpolation linéaire standard (méthode "R-7"/numpy par défaut) : pas
// besoin d'être identique bit à bit à l'agrégat SQL du cœur (spec §3.1) —
// juste d'un percentile usuel, pour rester visuellement cohérent d'une
// couche `vector` à une couche `feature`.
function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (idx - lower);
}

type Measure = { field: string; agg: string; label: string; p?: number };

// N'implémente que les trois agrégats que computeColorDomain/computeSizeDomain
// (mapSymbology.ts) émettent réellement : min, max, percentile. Les autres
// agrégats du catalogue SP-23 (avg, sum, countDistinct, median, stddev...) ne
// sont jamais demandés par ce chemin — les ajouter serait mort dès l'écriture.
export function makeStatQueryFn(fc: GeoJSON.FeatureCollection): StatQueryFn {
  return async (query) => {
    const groupBy = (query as { groupBy?: string }).groupBy;
    if (typeof groupBy === "string") {
      const seen = new Map<string, DataRecord>();
      for (const feature of fc.features) {
        const raw = (feature.properties ?? {})[groupBy];
        if (raw === undefined || raw === null) continue;
        const id = String(raw);
        if (!seen.has(id)) seen.set(id, { id, properties: {} });
      }
      return [...seen.values()];
    }
    const measures = (query as { measures?: Measure[] }).measures ?? [];
    const properties: Record<string, number> = {};
    for (const measure of measures) {
      const sorted = numericValues(fc, measure.field).sort((a, b) => a - b);
      if (measure.agg === "min") properties[measure.label] = sorted[0] ?? 0;
      else if (measure.agg === "max") properties[measure.label] = sorted[sorted.length - 1] ?? 0;
      else if (measure.agg === "percentile") {
        properties[measure.label] = percentile(sorted, measure.p ?? 0);
      }
    }
    return [{ id: "", properties }];
  };
}

export function makeSampleFieldFn(fc: GeoJSON.FeatureCollection): SampleFieldFn {
  return async (field, limit) => numericValues(fc, field).slice(0, limit);
}
