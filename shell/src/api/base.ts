// SPDX-License-Identifier: Apache-2.0
import type {
  CrossFilterLink,
  DataRecord,
  DatasetColumnMeta,
  FieldError,
  LayerSource,
  MapLayer,
  PopupConfig,
} from "./types";

// RawMapLayer/toFrontLayer vivent ici (et non dans domains/layers.ts) pour
// éviter un cycle itemClient.ts <-> domains/layers.ts : itemClient.ts
// ré-exporte les deux depuis ce module pour ne pas casser les imports
// externes existants (tests, `from "./itemClient"`).
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

// Erreurs partagées entre plusieurs domaines (features + exportsIngestion) :
// vivent ici, jamais dans un domains/*.ts, pour éviter qu'un domaine importe
// un autre domaine. itemClient.ts les ré-exporte pour ne pas casser les
// imports externes existants (`from "../../api/itemClient"`).
export class FeatureValidationError extends Error {
  errors: FieldError[];
  constructor(errors: FieldError[]) {
    super("feature validation failed");
    this.name = "FeatureValidationError";
    this.errors = errors;
  }
}

export class SqlQueryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SqlQueryError";
  }
}

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
  // GAP-65 (2/3) : pk === undefined vide tout le cache, sinon une seule
  // entrée. Ajoutée au-dessus de datasetCache (pas un remplacement) —
  // ne change pas le type public consommé directement par
  // domains/datasets.ts (createDatasetItem/saveDatasetConfig).
  invalidateDatasetCache(pk?: string): void;
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
  // SP-57b : point unique de redéfinition — l'API du cœur est versionnée
  // sous /v1 (health/mcp exceptés, jamais atteints par ce client). Tous les
  // consommateurs (request()/requestBlob() ci-dessous ET les fichiers de
  // domaine qui construisent leur propre fetch avec `base.coreUrl`, ex.
  // layers.ts/exportsIngestion.ts/extensionsAdminTools.ts/items.ts/
  // features.ts) lisent ce champ déjà versionné — aucun besoin d'éditer ces
  // fichiers individuellement (cf. spec SP-57b §1.3/§2.4).
  const coreUrl = `${opts.coreUrl}/v1`;
  const { getToken } = opts;

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
  // GAP-65 (2/3) : datasetCache lui-même ne change pas de forme (voir la
  // note de conception ci-dessus) — expiryByPk est une Map interne privée
  // à ce module, consultée uniquement par resolveDataset() pour décider si
  // l'entrée est encore valide. Un set() externe (createDatasetItem/
  // saveDatasetConfig dans domains/datasets.ts) ne pose jamais d'expiration
  // : une écriture fraîche après une sauvegarde réussie n'a pas besoin
  // d'expirer immédiatement.
  const DATASET_CACHE_TTL_MS = 5 * 60 * 1000;
  const expiryByPk = new Map<string, number>();

  function invalidateDatasetCache(pk?: string): void {
    if (pk === undefined) {
      datasetCache.clear();
      expiryByPk.clear();
      return;
    }
    datasetCache.delete(pk);
    expiryByPk.delete(pk);
  }

  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    const expiresAt = expiryByPk.get(pk);
    if (cached && expiresAt !== undefined && Date.now() < expiresAt) return cached;
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
    expiryByPk.set(pk, Date.now() + DATASET_CACHE_TTL_MS);
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
    invalidateDatasetCache,
    fetchGeoJsonFeatures,
    fetchCoreCollections,
    fetchExternalRasterSources,
    fetchHostedTileset3dSources,
    fetchHostedTerrain3dSources,
  };
}
