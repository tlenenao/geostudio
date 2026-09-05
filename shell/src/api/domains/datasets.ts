// SPDX-License-Identifier: Apache-2.0
import type {
  CollectionSchema,
  CreateDatasetInput,
  DataRecord,
  DataSource,
  DatasetConfig,
  Item,
  ItemClient,
} from "../types";
import type { ItemClientBase } from "../base";
import { requestBlob } from "../base";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

// Statistics config keys carried in DataSource.query; excluded from the fetch
// URL (they configure aggregation, not the feature request).
type StatMeasure = { field?: string; agg: string; label?: string; p?: number };

// Construit le corps JSON de POST /collections/{id}/aggregate depuis
// DataSource.query (SP-11b) — même vocabulaire que l'agrégation client
// supprimée par cette migration (groupBy/split/agg/field/measures), plus
// toute autre clé de query non reconnue traitée comme un filtre attributaire
// (même convention que buildFeaturesUrl pour une source "features").
const STAT_KEYS = new Set([
  "groupBy",
  "split",
  "agg",
  "field",
  "measures",
  "bbox",
  "bucket",
  "bins",
  "sample",
  "p",
]);

function parseBboxQueryValue(value: unknown): [number, number, number, number] | undefined {
  if (typeof value !== "string" || !value) return undefined;
  const parts = value.split(",").map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return undefined;
  return parts as [number, number, number, number];
}

function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (Array.isArray(query.groupBy)) body.groupBy = query.groupBy.map(String);
  else if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (query.bucket) body.bucket = String(query.bucket);
  if (query.bins) body.bins = Number(query.bins);
  if (query.sample) body.sample = Number(query.sample);
  if (query.p !== undefined && query.p !== null) body.p = Number(query.p);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined,
      agg: m.agg,
      label: m.label || undefined,
      p: m.p !== undefined ? m.p : undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
  if (query.geomIntersects && typeof query.geomIntersects === "object") {
    body.geomIntersects = query.geomIntersects;
  }
  const filters: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      filters[k] = String(v);
    }
  }
  if (Object.keys(filters).length) body.filters = filters;
  return body;
}

// Multi-field groupBy responses carry no single categorical key — this joins
// the group columns' values into a stable per-row id (single-field case
// unchanged: same as `String(row[categoryKey])` today).
function statRowId(row: Record<string, unknown>, categoryKey: string | string[]): string {
  if (Array.isArray(categoryKey)) return categoryKey.map((k) => String(row[k] ?? "")).join("|");
  return String(row[categoryKey] ?? "");
}

function _queryParams(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query).sort(([a], [b]) => a.localeCompare(b))) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      params.set(k, String(v));
    }
  }
  return params.toString();
}

function buildFeaturesUrl(coreUrl: string, source: DataSource): string {
  const base = `${coreUrl}/collections/${source.layer}/items`;
  const qs = _queryParams(source.query);
  return qs ? `${base}?${qs}` : base;
}

function buildArcgisItemsUrl(
  coreUrl: string,
  datasetItemId: string,
  query: Record<string, unknown>,
): string {
  const base = `${coreUrl}/datasets/${datasetItemId}/arcgis/items`;
  const qs = _queryParams(query);
  return qs ? `${base}?${qs}` : base;
}

type DatasetsMethods = Pick<
  ItemClient,
  | "createDatasetItem"
  | "getDatasetConfig"
  | "saveDatasetConfig"
  | "queryDataSource"
  | "featuresUrl"
  | "exportDataSource"
  | "getCollectionSchema"
>;

export function createDatasetsMethods(base: ItemClientBase): DatasetsMethods {
  const { request, coreUrl, getToken, resolveDataset, datasetCache, fetchGeoJsonFeatures } = base;
  return {
    async createDatasetItem(input: CreateDatasetInput): Promise<Item> {
      const dataset: DatasetConfig =
        input.source === "arcgis"
          ? { source: "arcgis", arcgisItemId: input.arcgisItemId, columns: {} }
          : { source: "collection", collectionId: input.collectionId, columns: {} };
      const config = { version: 1, kind: "dataset", dataset };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createDatasetItem: core returned no itemId");
      datasetCache.set(String(data.itemId), {
        source: dataset.source,
        collectionId: dataset.source === "collection" ? dataset.collectionId : null,
        arcgisItemId: dataset.source === "arcgis" ? dataset.arcgisItemId : null,
        columns: {},
        timeField: null,
        reactsToExtent: false,
        crossFilterLinks: [],
        sourcePipelineId: null,
      });
      return {
        pk: String(data.itemId),
        resourceType: "dataset",
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: "",
        configId: String(data.id),
        isPublished: false,
        license: "",
        language: "fr",
        // On vient de créer cet objet : on en est le propriétaire.
        permissions: OWNER_PERMISSIONS,
      };
    },

    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      if (resolved.source === "arcgis" && resolved.arcgisItemId) {
        return {
          source: "arcgis",
          arcgisItemId: resolved.arcgisItemId,
          columns: resolved.columns,
          timeField: resolved.timeField,
          reactsToExtent: resolved.reactsToExtent,
          crossFilterLinks: resolved.crossFilterLinks,
          sourcePipelineId: resolved.sourcePipelineId ?? null,
        };
      }
      return {
        source: "collection",
        collectionId: resolved.collectionId ?? "",
        columns: resolved.columns,
        timeField: resolved.timeField,
        reactsToExtent: resolved.reactsToExtent,
        crossFilterLinks: resolved.crossFilterLinks,
        sourcePipelineId: resolved.sourcePipelineId ?? null,
      };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: "dataset",
        dataset: config,
      });
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns,
        timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
        crossFilterLinks: config.crossFilterLinks ?? [],
        sourcePipelineId: config.sourcePipelineId ?? null,
      });
    },

    featuresUrl(source: DataSource): string {
      if (source.datasetId) {
        const cached = datasetCache.get(source.datasetId);
        if (cached?.source === "arcgis") {
          return buildArcgisItemsUrl(coreUrl, source.datasetId, source.query);
        }
        return buildFeaturesUrl(coreUrl, {
          ...source,
          layer: cached?.collectionId ?? source.layer,
        });
      }
      return buildFeaturesUrl(coreUrl, source);
    },

    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      if (cachedDataset?.source === "arcgis" && source.datasetId) {
        if (source.type === "statistics") {
          const body = buildAggregateBody(source.query);
          const data = await request<{
            categoryKey: string | string[];
            rows: Record<string, unknown>[];
          }>("POST", `/datasets/${source.datasetId}/arcgis/aggregate`, body);
          return data.rows.map((row) => ({
            id: statRowId(row, data.categoryKey),
            properties: row,
          }));
        }
        return fetchGeoJsonFeatures(buildArcgisItemsUrl(coreUrl, source.datasetId, source.query));
      }
      const resolved = source.datasetId
        ? { ...source, layer: cachedDataset?.collectionId ?? source.layer }
        : source;
      if (resolved.type === "static") {
        return (resolved.query.records as DataRecord[] | undefined) ?? [];
      }
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{
          categoryKey: string | string[];
          rows: Record<string, unknown>[];
        }>("POST", `/collections/${resolved.layer}/aggregate`, body);
        return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
      }
      return fetchGeoJsonFeatures(buildFeaturesUrl(coreUrl, resolved));
    },

    async exportDataSource(
      source: DataSource,
      format: string,
    ): Promise<{ blob: Blob; filename: string }> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      const isArcgis = cachedDataset?.source === "arcgis" && Boolean(source.datasetId);
      if (source.type === "statistics") {
        const body = buildAggregateBody(source.query);
        const path = isArcgis
          ? `/datasets/${source.datasetId}/arcgis/export?format=${format}`
          : `/collections/${cachedDataset?.collectionId ?? source.layer}/export?format=${format}`;
        return requestBlob(coreUrl, getToken, "POST", path, body);
      }
      const resolved = source.datasetId
        ? { ...source, layer: cachedDataset?.collectionId ?? source.layer }
        : source;
      const qs = _queryParams(resolved.query);
      const suffix = qs ? `&${qs}` : "";
      const path = isArcgis
        ? `/datasets/${source.datasetId}/arcgis/export/items?format=${format}${suffix}`
        : `/collections/${resolved.layer}/export/items?format=${format}${suffix}`;
      return requestBlob(coreUrl, getToken, "GET", path);
    },

    async getCollectionSchema(collectionId: string): Promise<CollectionSchema> {
      return request<CollectionSchema>("GET", `/collections/${collectionId}/schema`);
    },
  };
}
