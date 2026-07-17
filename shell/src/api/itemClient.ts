// SPDX-License-Identifier: Apache-2.0
import type { ActionMessage, AdminExtension, AppConfig, CandidateTable, CollectionAdmin, CollectionCreateInput, CollectionPatchInput, CollectionSchema, CreateKind, DataRecord, DataSource, ExtensionManifest, FieldError, GeoJSONFeatureInput, Group, InstanceInfo, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, Page, ResourceType, Sharing, Theme, UpdatePatch, Variable } from "./types";
import { DEFAULT_BASEMAP } from "../map/basemaps";
import { getTemplate } from "../builder/templates";

type RawMapLayer = {
  id: string; title: string; visible: boolean; kind: string;
  tilesUrl?: string | null; sourceLayer?: string | null; url?: string | null;
  opacity?: number | null; deckType?: string | null; dataUrl?: string | null;
  paint?: Record<string, unknown> | null; props?: Record<string, unknown> | null;
};

function toFrontLayer(l: RawMapLayer): MapLayer {
  const base = { id: l.id, title: l.title, visible: l.visible };
  switch (l.kind) {
    case "vector":
      return { ...base, kind: "vector", tilesUrl: l.tilesUrl ?? "", sourceLayer: l.sourceLayer ?? "",
        ...(l.paint ? { paint: l.paint } : {}) };
    case "raster":
      return { ...base, kind: "raster", tilesUrl: l.tilesUrl ?? "",
        ...(l.opacity != null ? { opacity: l.opacity } : {}) };
    case "deck":
      return { ...base, kind: "deck", deckType: (l.deckType ?? "heatmap") as "heatmap" | "hexbin" | "column",
        dataUrl: l.dataUrl ?? "", ...(l.props ? { props: l.props } : {}) };
    case "feature":
    default:
      return { ...base, kind: "feature", url: l.url ?? "", ...(l.paint ? { paint: l.paint } : {}) };
  }
}

// Statistics config keys carried in DataSource.query; excluded from the fetch
// URL (they configure client-side aggregation, not the feature request).
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures"]);

export class FeatureValidationError extends Error {
  errors: FieldError[];
  constructor(errors: FieldError[]) {
    super("feature validation failed");
    this.name = "FeatureValidationError";
    this.errors = errors;
  }
}

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
    const data = (await res.json().catch(() => null)) as { detail?: { errors?: FieldError[] } } | null;
    throw new FeatureValidationError(data?.detail?.errors ?? []);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof data?.detail === "string" ? data.detail : `Request failed: ${res.status} ${method} ${url}`;
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function buildFeaturesUrl(coreUrl: string, source: DataSource): string {
  const base = `${coreUrl}/collections/${source.layer}/items`;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(source.query).sort(([a], [b]) => a.localeCompare(b))) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      params.set(k, String(v));
    }
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

type StatMeasure = { field?: string; agg: string; label?: string };

function reduceValues(values: number[], agg: string): number {
  if (agg === "sum") return values.reduce((a, b) => a + b, 0);
  if (agg === "avg") return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  if (agg === "min") return values.length ? Math.min(...values) : 0;
  if (agg === "max") return values.length ? Math.max(...values) : 0;
  return values.length; // count
}

function measureLabel(m: StatMeasure): string {
  return m.label || (m.field ? `${m.agg}_${m.field}` : m.agg);
}

// Client-side aggregation for a "statistics" source. Emits a WIDE dataset — one
// row per groupBy category, one column per series — ready for an ECharts
// dataset. Series come from either a `split` field (pivot, single measure) or a
// list of measures (query.measures, else the single {agg, field}).
function aggregateRecords(records: DataRecord[], query: Record<string, unknown>): DataRecord[] {
  const groupBy = String(query.groupBy ?? "");
  const split = String(query.split ?? "");
  const categoryKey = groupBy || "group";
  const NUL = "\u0000";

  const categories: string[] = [];
  const catRows = new Map<string, Record<string, unknown>>();
  const ensureRow = (cat: string): Record<string, unknown> => {
    let row = catRows.get(cat);
    if (!row) {
      row = { [categoryKey]: cat };
      catRows.set(cat, row);
      categories.push(cat);
    }
    return row;
  };
  const catOf = (r: DataRecord): string => (groupBy ? String(r.properties[groupBy] ?? "") : "Total");

  if (split) {
    const agg = String(query.agg ?? "count");
    const field = String(query.field ?? "");
    const buckets = new Map<string, number[]>();
    const splitValues: string[] = [];
    const seenSplit = new Set<string>();
    for (const r of records) {
      const cat = catOf(r);
      ensureRow(cat);
      const sv = String(r.properties[split] ?? "");
      if (!seenSplit.has(sv)) { seenSplit.add(sv); splitValues.push(sv); }
      const key = `${cat}${NUL}${sv}`;
      const arr = buckets.get(key) ?? [];
      arr.push(Number(r.properties[field]) || 0);
      buckets.set(key, arr);
    }
    for (const cat of categories) {
      const row = catRows.get(cat)!;
      for (const sv of splitValues) {
        row[sv] = reduceValues(buckets.get(`${cat}${NUL}${sv}`) ?? [], agg);
      }
    }
  } else {
    const rawMeasures = Array.isArray(query.measures) ? (query.measures as StatMeasure[]) : [];
    const measures: StatMeasure[] = rawMeasures.length
      ? rawMeasures
      : [{ field: String(query.field ?? ""), agg: String(query.agg ?? "count"), label: "value" }];
    const buckets = new Map<string, number[]>();
    for (const r of records) {
      const cat = catOf(r);
      ensureRow(cat);
      measures.forEach((m, mi) => {
        const key = `${cat}${NUL}${mi}`;
        const arr = buckets.get(key) ?? [];
        arr.push(Number(r.properties[m.field ?? ""]) || 0);
        buckets.set(key, arr);
      });
    }
    for (const cat of categories) {
      const row = catRows.get(cat)!;
      measures.forEach((m, mi) => {
        row[measureLabel(m)] = reduceValues(buckets.get(`${cat}${NUL}${mi}`) ?? [], m.agg);
      });
    }
  }

  return categories.map((cat) => ({ id: cat, properties: catRows.get(cat)! }));
}

export function createItemClient(opts: {
  coreUrl: string;
  martinUrl?: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { coreUrl, martinUrl, getToken } = opts;

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

  async function fetchMartinSources(q?: string): Promise<LayerSource[]> {
    if (!martinUrl) return [];
    const res = await fetch(`${martinUrl}/catalog`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /catalog`);
    const data = (await res.json()) as {
      tiles?: Record<string, { description?: string }>;
    };
    const sources = Object.entries(data.tiles ?? {}).map(([id, meta]) => ({
      id,
      title: meta.description ?? id,
      service: "martin" as const,
      kind: "vector" as const,
      tilesUrl: `${martinUrl}/${id}/{z}/{x}/{y}`,
      sourceLayer: id,
    }));
    if (!q) return sources;
    const needle = q.toLowerCase();
    return sources.filter((s) => s.title.toLowerCase().includes(needle));
  }

  async function fetchCoreCollections(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/collections${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string; featureCount?: number | null }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "feature" as const,
      url: `${coreUrl}/collections/${c.id}/items`,
      featureCount: c.featureCount,
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

    async getMe(): Promise<Me> {
      const data = await request<{ username: string; firstName: string; lastName: string; isAdmin: boolean }>(
        "GET", `/me`,
      );
      return { username: data.username, firstName: data.firstName, lastName: data.lastName, isAdmin: data.isAdmin };
    },

    async getInstanceInfo(): Promise<InstanceInfo> {
      return request<InstanceInfo>("GET", "/instance");
    },

    async createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item> {
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: template?.dataSources ?? [],
        layout: template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: template?.messages ?? [],
      };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) {
        throw new Error("createConfigItem: core returned no itemId");
      }
      return {
        pk: String(data.itemId),
        resourceType: data.kind as ResourceType,
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: "",
        configId: String(data.id),
        isPublished: false,
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
        fetchMartinSources(params?.q),
        fetchCoreCollections(params?.q),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },

    async listActiveExtensions(): Promise<ExtensionManifest[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string; tag: string; label: string; moduleUrl: string;
          props: ExtensionManifest["props"]; events?: string[]; actions?: string[];
          defaultSize: { w: number; h: number }; permissions?: { collections: string[] | "all" };
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id, tag: e.tag, label: e.label, moduleUrl: e.moduleUrl,
        props: e.props, events: e.events, actions: e.actions,
        defaultSize: e.defaultSize, permissions: e.permissions,
      }));
    },

    async listAllExtensions(): Promise<AdminExtension[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions?all=true`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string; tag: string; label: string; moduleUrl: string;
          props: ExtensionManifest["props"]; events?: string[]; actions?: string[];
          defaultSize: { w: number; h: number }; permissions?: { collections: string[] | "all" };
          enabled: boolean;
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id, tag: e.tag, label: e.label, moduleUrl: e.moduleUrl,
        props: e.props, events: e.events, actions: e.actions,
        defaultSize: e.defaultSize, permissions: e.permissions, enabled: e.enabled,
      }));
    },

    async setExtensionEnabled(id: string, enabled: boolean): Promise<void> {
      await request<void>("PATCH", `/extensions/${id}`, { enabled });
    },

    async listCollections(): Promise<CollectionAdmin[]> {
      const data = await request<{ collections: CollectionAdmin[] }>("GET", `/collections`);
      return data.collections ?? [];
    },

    async listCandidateTables(): Promise<CandidateTable[]> {
      const data = await request<{ candidates: CandidateTable[] }>("GET", `/collections/candidates`);
      return data.candidates ?? [];
    },

    async createCollection(input: CollectionCreateInput): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("POST", `/collections`, input);
    },

    async updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("PATCH", `/collections/${id}`, patch);
    },

    async deleteCollection(id: string): Promise<void> {
      await request<void>("DELETE", `/collections/${id}`);
    },

    async getCollectionSharing(id: string): Promise<Sharing> {
      return request<Sharing>("GET", `/collections/${id}/sharing`);
    },

    async setCollectionSharing(id: string, sharing: Sharing): Promise<void> {
      await request<void>("PUT", `/collections/${id}/sharing`, sharing);
    },

    async createMapItem(input: { title: string; owner: string }): Promise<Item> {
      const map: MapConfig = {
        basemap: { style: DEFAULT_BASEMAP.style },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
      const config = { version: 1, kind: "map", map };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createMapItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "map", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map.
      const data = await request<{
        config?: { map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
      };
    },

    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "map", map: config });
    },

    async getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig> {
      const qs = mode ? `?mode=${mode}` : "";
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
        };
      }>("GET", `/configs/by-item/${pk}${qs}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
      };
    },

    async saveAppConfig(pk: string, config: AppConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: config.kind,
        theme: config.theme,
        dataSources: config.dataSources,
        messages: config.messages,
        pages: config.pages,
        variables: config.variables,
        layout: config.layout,
      });
    },

    featuresUrl(source: DataSource): string {
      return buildFeaturesUrl(coreUrl, source);
    },

    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      if (source.type === "static") {
        return (source.query.records as DataRecord[] | undefined) ?? [];
      }
      const token = getToken();
      const res = await fetch(buildFeaturesUrl(coreUrl, source), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${source.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      const records = (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
      return source.type === "statistics" ? aggregateRecords(records, source.query) : records;
    },

    async getCollectionSchema(collectionId: string): Promise<CollectionSchema> {
      return request<CollectionSchema>("GET", `/collections/${collectionId}/schema`);
    },

    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ canWrite?: boolean }>("GET", `/collections/${collectionId}`);
      return data.canWrite ?? false;
    },

    async createFeature(collectionId: string, feature: GeoJSONFeatureInput): Promise<{ id: string | number }> {
      return requestFeatureWrite<{ id: string | number }>(
        `${coreUrl}/collections/${collectionId}/items`, "POST", getToken(), feature,
      );
    },

    async updateFeature(collectionId: string, fid: string, feature: GeoJSONFeatureInput): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`, "PUT", getToken(), feature,
      );
    },

    async deleteFeature(collectionId: string, fid: string): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`, "DELETE", getToken(),
      );
    },

    async presignUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>(
        "POST", "/uploads/presign", { filename, contentType },
      );
    },

    async uploadToPresignedUrl(url: string, file: File) {
      const res = await fetch(url, { method: "PUT", body: file });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    },

    async inspectUpload(input: { key: string; filename: string }) {
      return request<{
        layers: { name: string; featureCount: number; geometryType: string }[];
      }>("POST", "/uploads/inspect", input);
    },

    async createIngestionJob(input) {
      return request<{ jobId: string }>("POST", "/uploads", input);
    },

    async getIngestionJob(jobId: string) {
      return request<{
        status: "pending" | "running" | "done" | "error";
        errorMessage: string | null;
        collectionId: string | null;
        itemId: string | null;
      }>("GET", `/uploads/${jobId}`);
    },
  };
}
