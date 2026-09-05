// SPDX-License-Identifier: Apache-2.0
import type { CrossFilterLink, DataRecord, DatasetColumnMeta, LayerSource } from "./types";

export type ResolvedDataset = {
  source: "collection" | "arcgis";
  collectionId: string | null;
  arcgisItemId: string | null;
  columns: Record<string, DatasetColumnMeta>;
  timeField: string | null;
  reactsToExtent: boolean;
  crossFilterLinks: CrossFilterLink[];
  sourcePipelineId: string | null;
};

export type ItemClientBase = {
  coreUrl: string;
  getToken: () => string | undefined;
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  resolveDataset(pk: string): Promise<ResolvedDataset>;
  datasetCache: Map<string, ResolvedDataset>;
  fetchGeoJsonFeatures(url: string): Promise<DataRecord[]>;
  fetchCoreCollections(q?: string): Promise<LayerSource[]>;
  fetchExternalRasterSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTileset3dSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTerrain3dSources(q?: string): Promise<{ id: string; title: string }[]>;
};

// Une collection sort désormais en couche TUILÉE servie par le cœur (SP-24) :
// elle passe à l'échelle, elle est autorisée par can(), et elle porte son
// collectionId — ce dont le popup et la symbologie SP-25 ont besoin.
export const GEOMETRY_KINDS: Record<string, "point" | "line" | "polygon"> = {
  Point: "point",
  MultiPoint: "point",
  LineString: "line",
  MultiLineString: "line",
  Polygon: "polygon",
  MultiPolygon: "polygon",
};

export async function requestBlob(
  coreUrl: string,
  getToken: () => string | undefined,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${coreUrl}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${method} ${path}`);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match ? match[1] : "export";
  const blob = await res.blob();
  return { blob, filename };
}

export function createBase(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
}): ItemClientBase {
  const { coreUrl, getToken } = opts;

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${coreUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${method} ${path}`);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  const datasetCache = new Map<string, ResolvedDataset>();

  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: {
        dataset?: {
          source: "collection" | "arcgis";
          collectionId?: string | null;
          arcgisItemId?: string | null;
          columns?: Record<string, DatasetColumnMeta>;
          timeField?: string | null;
          reactsToExtent?: boolean;
          crossFilterLinks?: CrossFilterLink[];
          sourcePipelineId?: string | null;
        } | null;
      };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      source: dataset.source,
      collectionId: dataset.collectionId ?? null,
      arcgisItemId: dataset.arcgisItemId ?? null,
      columns: dataset.columns ?? {},
      timeField: dataset.timeField ?? null,
      reactsToExtent: dataset.reactsToExtent ?? false,
      crossFilterLinks: dataset.crossFilterLinks ?? [],
      sourcePipelineId: dataset.sourcePipelineId ?? null,
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }

  async function fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    const token = getToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error(`Request failed: ${res.status} features`);
    const data = (await res.json()) as {
      features?: {
        id?: string | number;
        properties?: Record<string, unknown>;
        geometry?: unknown;
      }[];
    };
    return (data.features ?? []).map((f, i) => ({
      id: f.id ?? i,
      properties: f.properties ?? {},
      geometry: f.geometry,
    }));
  }

  async function fetchCoreCollections(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/collections${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: {
        id: string;
        title?: string;
        featureCount?: number | null;
        geometryType?: string | null;
        pkColumn?: string | null;
      }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "vector" as const,
      tilesUrl: `${coreUrl}/collections/${c.id}/tiles/{z}/{x}/{y}.mvt`,
      sourceLayer: c.id,
      collectionId: c.id,
      geometryKind: c.geometryType ? GEOMETRY_KINDS[c.geometryType] : undefined,
      pkColumn: c.pkColumn ?? undefined,
      featureCount: c.featureCount,
    }));
  }

  async function fetchExternalRasterSources(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/harvest/layers${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /harvest/layers`);
    const data = (await res.json()) as {
      layers?: { id: string; title: string; kind: "raster"; tilesUrl: string }[];
    };
    return (data.layers ?? []).map((l) => ({
      id: l.id,
      title: l.title,
      service: "external" as const,
      kind: "raster" as const,
      tilesUrl: l.tilesUrl,
    }));
  }

  async function fetchHostedTileset3dSources(q?: string): Promise<LayerSource[]> {
    const query = new URLSearchParams({ type: "tileset3d", pageSize: "200" });
    if (q) query.set("q", q);
    const token = getToken();
    const res = await fetch(`${coreUrl}/items?${query.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /items`);
    const data = (await res.json()) as { items?: { pk: string; title: string }[] };
    return (data.items ?? []).map((item) => ({
      id: item.pk,
      title: item.title,
      service: "tileset3d" as const,
      kind: "tiles3d" as const,
      url: `${coreUrl}/tileset3d/${item.pk}/tileset.json`,
    }));
  }

  async function fetchHostedTerrain3dSources(q?: string): Promise<{ id: string; title: string }[]> {
    const query = new URLSearchParams({ type: "terrain3d", pageSize: "200" });
    if (q) query.set("q", q);
    const token = getToken();
    const res = await fetch(`${coreUrl}/items?${query.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /items`);
    const data = (await res.json()) as { items?: { pk: string; title: string }[] };
    return (data.items ?? []).map((item) => ({ id: item.pk, title: item.title }));
  }

  return {
    coreUrl,
    getToken,
    request,
    resolveDataset,
    datasetCache,
    fetchGeoJsonFeatures,
    fetchCoreCollections,
    fetchExternalRasterSources,
    fetchHostedTileset3dSources,
    fetchHostedTerrain3dSources,
  };
}
