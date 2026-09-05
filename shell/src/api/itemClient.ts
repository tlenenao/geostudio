// SPDX-License-Identifier: Apache-2.0
import type {
  BookmarkPayload,
  CollectionAdmin,
  CollectionSchema,
  ConfigRevisionInfo,
  CreateKind,
  CreateBookmarkInput,
  CreateDatasetInput,
  CrossFilterLink,
  DataRecord,
  DataSource,
  DatasetColumnMeta,
  DatasetConfig,
  FeatureLayerSource,
  FieldError,
  GeoJSONFeatureInput,
  Group,
  InstanceInfo,
  Item,
  ItemClient,
  ItemPage,
  LayerSource,
  ListItemsParams,
  MapConfig,
  MapIconOut,
  MapLayer,
  MetadataCatalog,
  PopupConfig,
  PrintLayoutConfig,
  ResourceType,
  Sharing,
  UpdatePatch,
} from "./types";
import { DEFAULT_BASEMAP } from "../map/basemaps";
import { getTemplate } from "../builder/templates";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { createBase, FeatureValidationError, SqlQueryError } from "./base";
import { createAlertsMethods } from "./domains/alerts";
import { createAppsMethods } from "./domains/apps";
import { createAttachmentsMethods } from "./domains/attachments";
import { createCollectionsAdminMethods } from "./domains/collectionsAdmin";
import { createExportsIngestionMethods } from "./domains/exportsIngestion";
import { createExtensionsAdminToolsMethods } from "./domains/extensionsAdminTools";
import { createIdentityMethods } from "./domains/identity";
import { createNotificationsMethods } from "./domains/notifications";
import { createPipelinesMethods } from "./domains/pipelines";
import { createReportsMethods } from "./domains/reports";
import { createTiles3dMethods } from "./domains/tiles3d";

export type RawMapLayer = {
  id: string;
  title: string;
  visible: boolean;
  kind: string;
  tilesUrl?: string | null;
  sourceLayer?: string | null;
  url?: string | null;
  opacity?: number | null;
  deckType?: string | null;
  dataUrl?: string | null;
  paint?: Record<string, unknown> | null;
  props?: Record<string, unknown> | null;
  popup?: PopupConfig | null;
  collectionId?: string | null;
  geometryKind?: "point" | "line" | "polygon" | null;
  pkColumn?: string | null;
  renderAs?: "fill" | "circle" | "line" | null;
  symbology?: import("../builder/widgets/mapSymbology").LayerSymbology | null;
};

export function toFrontLayer(l: RawMapLayer): MapLayer {
  const base = { id: l.id, title: l.title, visible: l.visible };
  switch (l.kind) {
    case "vector":
      return {
        ...base,
        kind: "vector",
        tilesUrl: l.tilesUrl ?? "",
        sourceLayer: l.sourceLayer ?? "",
        ...(l.paint ? { paint: l.paint } : {}),
        ...(l.collectionId ? { collectionId: l.collectionId } : {}),
        ...(l.geometryKind ? { geometryKind: l.geometryKind } : {}),
        ...(l.pkColumn ? { pkColumn: l.pkColumn } : {}),
        ...(l.popup ? { popup: l.popup } : {}),
        ...(l.symbology ? { symbology: l.symbology } : {}),
      };
    case "raster":
      return {
        ...base,
        kind: "raster",
        tilesUrl: l.tilesUrl ?? "",
        ...(l.opacity != null ? { opacity: l.opacity } : {}),
      };
    case "deck":
      return {
        ...base,
        kind: "deck",
        deckType: (l.deckType ?? "heatmap") as "heatmap" | "hexbin" | "column",
        dataUrl: l.dataUrl ?? "",
        ...(l.props ? { props: l.props } : {}),
      };
    case "tiles3d":
      return { ...base, kind: "tiles3d", url: l.url ?? "" };
    case "feature":
    default:
      return {
        ...base,
        kind: "feature",
        url: l.url ?? "",
        ...(l.paint ? { paint: l.paint } : {}),
        ...(l.collectionId ? { collectionId: l.collectionId } : {}),
        ...(l.pkColumn ? { pkColumn: l.pkColumn } : {}),
        ...(l.popup ? { popup: l.popup } : {}),
        ...(l.renderAs ? { renderAs: l.renderAs } : {}),
        ...(l.symbology ? { symbology: l.symbology } : {}),
      };
  }
}

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

export { FeatureValidationError, SqlQueryError };

async function requestFeatureWrite<T>(
  url: string,
  method: string,
  token: string | undefined,
  body?: GeoJSONFeatureInput,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { errors?: FieldError[] } | null;
    throw new FeatureValidationError(data?.errors ?? []);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : `Request failed: ${res.status} ${method} ${url}`;
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(
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

export function createItemClient(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { coreUrl, getToken } = opts;
  const base = createBase(opts);

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

  type ResolvedDataset = {
    source: "collection" | "arcgis";
    collectionId: string | null;
    arcgisItemId: string | null;
    columns: Record<string, DatasetColumnMeta>;
    timeField: string | null;
    reactsToExtent: boolean;
    crossFilterLinks: CrossFilterLink[];
    sourcePipelineId: string | null;
  };
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

  async function _fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
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

  // Une collection sort désormais en couche TUILÉE servie par le cœur (SP-24) :
  // elle passe à l'échelle, elle est autorisée par can(), et elle porte son
  // collectionId — ce dont le popup et la symbologie SP-25 ont besoin.
  const GEOMETRY_KINDS: Record<string, "point" | "line" | "polygon"> = {
    Point: "point",
    MultiPoint: "point",
    LineString: "line",
    MultiLineString: "line",
    Polygon: "polygon",
    MultiPolygon: "polygon",
  };

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

  return {
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("q", params.q);
      if (params.type) q.set("type", params.type);
      if (params.scope) q.set("scope", params.scope);
      q.set("page", String(params.page ?? 1));
      q.set("pageSize", String(params.pageSize ?? 12));
      return request<ItemPage>("GET", `/items?${q.toString()}`);
    },

    async getItem(pk: string): Promise<Item> {
      return request<Item>("GET", `/items/${pk}`);
    },

    async getMetadataCatalog(): Promise<MetadataCatalog> {
      return request<MetadataCatalog>("GET", "/metadata-catalog");
    },

    async getItemBySlug(slug: string): Promise<Item> {
      return request<Item>("GET", `/public/sites/${encodeURIComponent(slug)}`);
    },

    async listPublicItems(
      params: { type?: ResourceType; tag?: string; page?: number; pageSize?: number } = {},
    ): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.type) q.set("type", params.type);
      if (params.tag) q.set("tag", params.tag);
      q.set("page", String(params.page ?? 1));
      q.set("pageSize", String(params.pageSize ?? 12));
      return request<ItemPage>("GET", `/public/items?${q.toString()}`);
    },

    ...createIdentityMethods(base),
    ...createNotificationsMethods(base),

    async getInstanceInfo(): Promise<InstanceInfo> {
      return request<InstanceInfo>("GET", "/instance");
    },

    async createConfigItem(input: {
      kind: CreateKind;
      title: string;
      owner: string;
      templateId?: string;
      slug?: string;
    }): Promise<Item> {
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const firstPageLayout = template?.pages?.[0]?.layout;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: template?.dataSources ?? [],
        layout: firstPageLayout ?? template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: template?.messages ?? [],
        pages: template?.pages ?? [],
        navigationMode: template?.navigationMode ?? "tabs",
        interactions: "auto",
      };
      const payload: Record<string, unknown> = { title: input.title, config };
      if (input.slug) payload.slug = input.slug;
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        payload,
      );
      if (!data.itemId) {
        throw new Error("createConfigItem: core returned no itemId");
      }
      return {
        pk: String(data.itemId),
        resourceType: data.kind as ResourceType,
        slug: input.slug,
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

    async updateItem(pk: string, patch: UpdatePatch): Promise<Item> {
      return request<Item>("PATCH", `/items/${pk}`, patch);
    },

    async uploadThumbnail(pk: string, file: File): Promise<void> {
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${coreUrl}/items/${pk}/thumbnail`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} POST thumbnail`);
      }
    },

    async deleteItem(pk: string): Promise<void> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/configs/by-item/${pk}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(`Request failed: ${res.status} DELETE /configs/by-item/${pk}`);
      }
    },

    async listGroups(): Promise<Group[]> {
      const data = await request<{ id: string; name: string }[]>("GET", `/groups`);
      return data.map((g) => ({ id: g.id, title: g.name }));
    },

    async getSharing(pk: string): Promise<Sharing> {
      return request<Sharing>("GET", `/items/${pk}/sharing`);
    },

    async setSharing(pk: string, sharing: Sharing): Promise<void> {
      await request<void>("PUT", `/items/${pk}/sharing`, sharing);
    },

    async listLayerSources(params?: { q?: string }): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchCoreCollections(params?.q),
        fetchExternalRasterSources(params?.q),
        fetchHostedTileset3dSources(params?.q),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },

    async listFeatureLayers(params: { q?: string } = {}): Promise<FeatureLayerSource[]> {
      const token = getToken();
      const query = params.q ? `?q=${encodeURIComponent(params.q)}` : "";
      const res = await fetch(`${coreUrl}/harvest/feature-layers${query}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /harvest/feature-layers`);
      const data = (await res.json()) as { layers?: FeatureLayerSource[] };
      return data.layers ?? [];
    },

    ...createExtensionsAdminToolsMethods(base),

    ...createCollectionsAdminMethods(base),

    async createMapItem(input: { title: string; owner: string }): Promise<Item> {
      const map: MapConfig = {
        basemap: { style: DEFAULT_BASEMAP.style },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
      const config = { version: 1, kind: "map", map };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createMapItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: "map",
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

    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map,
      // printLayout is a sibling top-level field (core/app/configs/schemas.py::BuilderConfig).
      const data = await request<{
        config?: {
          map?: {
            basemap: { style: string };
            view: {
              center: [number, number];
              zoom: number;
              pitch?: number | null;
              bearing?: number | null;
            };
            layers: RawMapLayer[];
            terrain?: {
              tilesUrl: string;
              encoding: "terrarium";
              exaggeration?: number | null;
            } | null;
          } | null;
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: {
          center: map.view.center,
          zoom: map.view.zoom,
          ...(map.view.pitch != null ? { pitch: map.view.pitch } : {}),
          ...(map.view.bearing != null ? { bearing: map.view.bearing } : {}),
        },
        layers: (map.layers ?? []).map(toFrontLayer),
        printLayout: data.config?.printLayout ?? null,
        terrain: map.terrain
          ? {
              tilesUrl: map.terrain.tilesUrl,
              encoding: map.terrain.encoding,
              ...(map.terrain.exaggeration != null
                ? { exaggeration: map.terrain.exaggeration }
                : {}),
            }
          : null,
      };
    },

    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      const { printLayout, ...map } = config;
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: "map",
        map,
        printLayout: printLayout ?? null,
      });
    },

    async listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      const rows = await request<{ version: number; created_at: string }[]>(
        "GET",
        `/configs/${id}/revisions`,
      );
      return rows.map((r) => ({ version: r.version, createdAt: r.created_at }));
    },
    async rollbackConfig(pk: string, version: number): Promise<void> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      await request<unknown>("POST", `/configs/${id}/rollback`, { version });
    },

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

    async createBookmarkItem(input: CreateBookmarkInput): Promise<Item> {
      const bookmark: BookmarkPayload = {
        appId: input.appId,
        pageId: input.pageId,
        timeRange: input.timeRange,
        extent: input.extent,
        crossFilter: input.crossFilter,
      };
      const config = { version: 1, kind: "bookmark", bookmark };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createBookmarkItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: "bookmark",
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

    async getBookmarkConfig(pk: string): Promise<BookmarkPayload> {
      const data = await request<{ config?: { bookmark?: BookmarkPayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.bookmark)
        throw new Error("getBookmarkConfig: config has no bookmark payload");
      return data.config.bookmark;
    },

    ...createPipelinesMethods(base),

    ...createAlertsMethods(base),

    ...createReportsMethods(base),

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

    ...createAppsMethods(base),

    ...createExportsIngestionMethods(base),

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
        return _fetchGeoJsonFeatures(buildArcgisItemsUrl(coreUrl, source.datasetId, source.query));
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
      return _fetchGeoJsonFeatures(buildFeaturesUrl(coreUrl, resolved));
    },

    async sampleCollectionField(
      collectionId: string,
      field: string,
      limit: number,
    ): Promise<number[]> {
      const data = await request<{ categoryKey: string | string[]; rows: { value: number }[] }>(
        "POST",
        `/collections/${collectionId}/aggregate`,
        { field, sample: limit },
      );
      return data.rows.map((r) => Number(r.value));
    },

    async uploadMapIcon(file: File, title: string, category: string) {
      // Multipart, patron copié de uploadThumbnail (itemClient.ts:600-612) :
      // `request()` sérialise en JSON, donc fetch direct. On ne pose PAS
      // Content-Type à la main — la plateforme ajoute le boundary.
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      form.append("title", title);
      form.append("category", category);
      const res = await fetch(`${coreUrl}/map-icons`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        // Le cœur répond en RFC 7807 avec un membre `errors` de premier
        // niveau quand un SVG est refusé : remonter le message pour que
        // l'auteur voie POURQUOI, au lieu d'un code nu.
        let detail = "";
        try {
          const problem = (await res.json()) as {
            detail?: string;
            errors?: { message?: string }[];
          };
          detail = problem.errors?.[0]?.message ?? problem.detail ?? "";
        } catch {
          detail = "";
        }
        throw new Error(
          `Request failed: ${res.status} POST /map-icons${detail ? ` — ${detail}` : ""}`,
        );
      }
      return (await res.json()) as MapIconOut;
    },

    async listMapIcons() {
      return request<MapIconOut[]>("GET", "/map-icons");
    },

    async deleteMapIcon(iconId: string) {
      await request<void>("DELETE", `/map-icons/${encodeURIComponent(iconId)}`);
    },

    async fetchMapIconBlob(iconId: string) {
      // `request()` fait toujours res.json() : cette route renvoie des
      // octets, donc fetch direct, avec le même en-tête d'autorisation.
      const token = getToken();
      const res = await fetch(`${coreUrl}/map-icons/${encodeURIComponent(iconId)}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} GET /map-icons/${iconId}/file`);
      return res.blob();
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

    ...createAttachmentsMethods(base),

    async getCollection(collectionId: string): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("GET", `/collections/${collectionId}`);
    },

    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ permissions?: { write?: boolean } }>(
        "GET",
        `/collections/${collectionId}`,
      );
      return data.permissions?.write ?? false;
    },

    async createFeature(
      collectionId: string,
      feature: GeoJSONFeatureInput,
    ): Promise<{ id: string | number }> {
      return requestFeatureWrite<{ id: string | number }>(
        `${coreUrl}/collections/${collectionId}/items`,
        "POST",
        getToken(),
        feature,
      );
    },

    async updateFeature(
      collectionId: string,
      fid: string,
      feature: GeoJSONFeatureInput,
    ): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "PUT",
        getToken(),
        feature,
      );
    },

    async deleteFeature(collectionId: string, fid: string): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "DELETE",
        getToken(),
      );
    },

    ...createTiles3dMethods(base),

    getAuthToken: getToken,
    getCoreUrl: () => coreUrl,
  };
}
