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
import { CoreUnreachableError } from "./CoreUnreachableError";
import { ApiError } from "./ApiError";

// SP-B7 : borne toute requête cœur à 15s et convertit un fetch qui rejette
// (réseau coupé, timeout, DNS, etc.) en CoreUnreachableError — distingué
// d'une vraie erreur serveur (réponse HTTP non-ok, gérée par chaque appelant
// individuellement) pour que ConnectivityBanner puisse réagir spécifiquement
// à une injoignabilité, pas à n'importe quel échec de requête.
const DEFAULT_TIMEOUT_MS = 15_000;

// `timeoutMs` : surcharge ponctuelle pour les appels réputés longs côté
// cœur (ex. copilotTurn, domains/apps.ts) — tous les autres gardent 15s.
async function fetchWithTimeout(
  input: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  try {
    return await fetch(input, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  } catch (err) {
    throw new CoreUnreachableError(err);
  }
}

// AbortSignal.timeout() couvre tout le cycle de vie du fetch, lecture du
// corps comprise : un timeout qui tombe pendant res.json()/res.blob() rejette
// en DOMException AbortError HORS du try/catch de fetchWithTimeout. On le
// convertit en CoreUnreachableError (sinon ConnectivityBanner ne réagit pas) ;
// toute autre erreur (JSON invalide…) est relancée telle quelle.
async function readBody<T>(read: () => Promise<T>): Promise<T> {
  try {
    return await read();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new CoreUnreachableError(err);
    }
    throw err;
  }
}

// SP-B5 : le cœur répond en RFC 7807 (`application/problem+json`,
// `title`+`detail`) sur toute erreur HTTP, et porte un en-tête `Retry-After`
// (secondes) sur un 429 (`rate_limit_guard`, `core/app/main.py`). Partagé
// entre `request()` et `requestBlob()` : les deux jettent aujourd'hui une
// `Error` générique sur `!res.ok`, jetant ces champs. `res.clone()` est
// nécessaire car le corps ne se lit qu'une fois — un appelant qui a déjà lu
// `res` (aucun cas actuel) casserait sinon.
export async function parseErrorResponse(res: Response): Promise<ApiError> {
  let title: string | undefined;
  let detail: string | undefined;
  let errors: FieldError[] | undefined;
  let problemType: string | undefined;
  let quota: { kind: string; current: number; limit: number } | undefined;
  try {
    const problem = (await res.clone().json()) as {
      title?: unknown;
      detail?: unknown;
      errors?: unknown;
      type?: unknown;
      quota?: unknown;
      current?: unknown;
      limit?: unknown;
    };
    if (problem.type === "quota-exceeded") {
      problemType = problem.type;
      quota = {
        kind: String(problem.quota),
        current: Number(problem.current),
        limit: Number(problem.limit),
      };
    }
    if (typeof problem.title === "string") title = problem.title;
    if (typeof problem.detail === "string") detail = problem.detail;
    if (Array.isArray(problem.errors)) errors = problem.errors as FieldError[];
  } catch {
    // Corps absent ou non-JSON (ex. 500 sans body) : ApiError retombe sur
    // son message générique plutôt que de faire échouer la gestion d'erreur.
  }
  const retryAfterHeader = res.headers.get("Retry-After");
  const retryAfter =
    res.status === 429 && retryAfterHeader !== null && !Number.isNaN(Number(retryAfterHeader))
      ? Number(retryAfterHeader)
      : undefined;
  return new ApiError(res.status, { title, detail, retryAfter, errors, problemType, quota });
}

// P22.04 : garde `!res.ok` unique des sites qui font leur propre fetch (via
// authFetch) — jette l'ApiError RFC 7807 au lieu d'une Error « Request failed ».
export async function ensureOk(res: Response): Promise<Response> {
  if (!res.ok) throw await parseErrorResponse(res);
  return res;
}

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

// P22.02 : tout champ non nul du cœur survit au round-trip (le PUT de
// saveMapConfig est complet) — les variantes ci-dessous ne fixent que les
// défauts/normalisations propres à chaque kind.
export function toFrontLayer(l: RawMapLayer): MapLayer {
  const extra = Object.fromEntries(Object.entries(l).filter(([, v]) => v != null));
  return { ...extra, ...toFrontLayerKind(l) } as MapLayer;
}

function toFrontLayerKind(l: RawMapLayer): MapLayer {
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
  getShareLinkToken?: () => string | undefined;
  request<T>(
    method: string,
    path: string,
    body?: unknown,
    timeoutMs?: number,
    extraHeaders?: Record<string, string>,
  ): Promise<T>;
  // P07.06 : fetch authentifié (Authorization + renouvellement silencieux sur
  // 401, rejeu unique) pour les sites qui ne passent pas par request().
  authFetch(url: string, init?: RequestInit, timeoutMs?: number): Promise<Response>;
  // P30.03 : GET d'une URL arbitraire (tuile, GeoJSON). `authenticated` = URL
  // servie par le cœur (jeton de session ou de lien de partage) ; sinon requête
  // nue, jamais de jeton vers un hôte libre.
  fetchUrl(url: string, opts?: { authenticated?: boolean }): Promise<Response>;
  // Renouvellement partagé (undefined = pas de renouvellement possible).
  renewToken?: () => Promise<string | undefined>;
  resolveDataset(pk: string): Promise<ResolvedDataset>;
  datasetCache: Map<string, ResolvedDataset>;
  // GAP-65 (2/3) : pk === undefined vide tout le cache, sinon une seule
  // entrée. Ajoutée au-dessus de datasetCache (pas un remplacement) —
  // ne change pas le type public consommé directement par
  // domains/datasets.ts (createDatasetItem/saveDatasetConfig).
  invalidateDatasetCache(pk?: string): void;
  fetchGeoJsonFeatures(url: string): Promise<DataRecord[]>;
  // P29.05 : idem avec `numberMatched` du cœur (total hors page), null si absent.
  fetchGeoJsonPage(url: string): Promise<{ records: DataRecord[]; total: number | null }>;
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
  getShareLinkToken?: () => string | undefined,
  renewToken?: () => Promise<string | undefined>,
): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const shareToken = getShareLinkToken?.();
  const send = (tok: string | undefined) => {
    const headers: Record<string, string> = {};
    if (tok) headers.Authorization = `Bearer ${tok}`;
    else if (shareToken) headers["X-Share-Link-Token"] = shareToken;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    return fetchWithTimeout(`${coreUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };
  let res = await send(token);
  if (res.status === 401 && token && renewToken) {
    const fresh = await renewToken();
    if (fresh) res = await send(fresh);
  }
  if (!res.ok) throw await parseErrorResponse(res);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match ? match[1] : "export";
  const blob = await readBody(() => res.blob());
  return { blob, filename };
}

export function createBase(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
  getShareLinkToken?: () => string | undefined;
  // P07.06 : appelé sur un 401 d'une requête authentifiée. Renvoie un jeton
  // frais (renouvellement silencieux) ; undefined = session perdue (l'appelant
  // a alors déjà déclenché la reconnexion). La requête n'est rejouée qu'une fois.
  onUnauthorized?: () => Promise<string | undefined>;
}): ItemClientBase {
  // SP-57b : point unique de redéfinition — l'API du cœur est versionnée
  // sous /v1 (health/mcp exceptés, jamais atteints par ce client). Tous les
  // consommateurs (request()/requestBlob() ci-dessous ET les fichiers de
  // domaine qui construisent leur propre fetch avec `base.coreUrl`, ex.
  // layers.ts/exportsIngestion.ts/extensionsAdminTools.ts/items.ts/
  // features.ts) lisent ce champ déjà versionné — aucun besoin d'éditer ces
  // fichiers individuellement (cf. spec SP-57b §1.3/§2.4).
  const coreUrl = `${opts.coreUrl}/v1`;
  const { getToken, getShareLinkToken, onUnauthorized } = opts;
  // Un seul renouvellement à la fois : N requêtes parallèles en 401 partagent
  // la même promesse.
  let renewing: Promise<string | undefined> | null = null;
  function renewOnce(): Promise<string | undefined> {
    renewing ??= onUnauthorized!().finally(() => {
      renewing = null;
    });
    return renewing;
  }

  async function authFetch(
    url: string,
    init: RequestInit = {},
    timeoutMs?: number,
  ): Promise<Response> {
    const send = (tok: string | undefined) => {
      const headers = new Headers(init.headers);
      if (tok) headers.set("Authorization", `Bearer ${tok}`);
      return fetchWithTimeout(url, { ...init, headers }, timeoutMs);
    };
    const token = getToken();
    let res = await send(token);
    if (res.status === 401 && token && onUnauthorized) {
      const fresh = await renewOnce();
      if (fresh) res = await send(fresh);
    }
    return res;
  }

  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    timeoutMs?: number,
    extraHeaders?: Record<string, string>,
  ): Promise<T> {
    const shareToken = getShareLinkToken?.();
    const send = (token: string | undefined) => {
      const headers: Record<string, string> = { ...extraHeaders };
      if (token) headers.Authorization = `Bearer ${token}`;
      if (shareToken) headers["X-Share-Link-Token"] = shareToken;
      if (body !== undefined) headers["Content-Type"] = "application/json";
      return fetchWithTimeout(
        `${coreUrl}${path}`,
        {
          method,
          headers,
          body: body !== undefined ? JSON.stringify(body) : undefined,
        },
        timeoutMs,
      );
    };
    const token = getToken();
    let res = await send(token);
    if (res.status === 401 && token && onUnauthorized) {
      const fresh = await renewOnce();
      if (fresh) res = await send(fresh);
    }
    if (!res.ok) {
      throw await parseErrorResponse(res);
    }
    if (res.status === 204) return undefined as T;
    return readBody(() => res.json() as Promise<T>);
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

  async function fetchUrl(url: string, opts?: { authenticated?: boolean }): Promise<Response> {
    if (!opts?.authenticated) return fetchWithTimeout(url);
    const shareToken = getShareLinkToken?.();
    return authFetch(url, shareToken ? { headers: { "X-Share-Link-Token": shareToken } } : {});
  }

  async function fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    return (await fetchGeoJsonPage(url)).records;
  }

  async function fetchGeoJsonPage(
    url: string,
  ): Promise<{ records: DataRecord[]; total: number | null }> {
    const shareToken = getShareLinkToken?.();
    const headers: Record<string, string> = {};
    if (shareToken) headers["X-Share-Link-Token"] = shareToken;
    const res = await authFetch(url, { headers });
    await ensureOk(res);
    const data = (await res.json()) as {
      numberMatched?: number;
      features?: {
        id?: string | number;
        properties?: Record<string, unknown>;
        geometry?: unknown;
      }[];
    };
    const records = (data.features ?? []).map((f, i) => ({
      id: f.id ?? i,
      properties: f.properties ?? {},
      geometry: f.geometry,
    }));
    return { records, total: typeof data.numberMatched === "number" ? data.numberMatched : null };
  }

  async function fetchCoreCollections(q?: string): Promise<LayerSource[]> {
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await authFetch(`${coreUrl}/collections${query}`);
    await ensureOk(res);
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
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await authFetch(`${coreUrl}/harvest/layers${query}`);
    await ensureOk(res);
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
    const res = await authFetch(`${coreUrl}/items?${query.toString()}`);
    await ensureOk(res);
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
    const res = await authFetch(`${coreUrl}/items?${query.toString()}`);
    await ensureOk(res);
    const data = (await res.json()) as { items?: { pk: string; title: string }[] };
    return (data.items ?? []).map((item) => ({ id: item.pk, title: item.title }));
  }

  return {
    coreUrl,
    getToken,
    getShareLinkToken,
    request,
    authFetch,
    renewToken: onUnauthorized ? renewOnce : undefined,
    resolveDataset,
    datasetCache,
    invalidateDatasetCache,
    fetchUrl,
    fetchGeoJsonFeatures,
    fetchGeoJsonPage,
    fetchCoreCollections,
    fetchExternalRasterSources,
    fetchHostedTileset3dSources,
    fetchHostedTerrain3dSources,
  };
}
