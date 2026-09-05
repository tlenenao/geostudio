// SPDX-License-Identifier: Apache-2.0
import type {
  FeatureLayerSource,
  Item,
  ItemClient,
  LayerSource,
  MapConfig,
  MapIconOut,
  PrintLayoutConfig,
} from "../types";
import type { ItemClientBase, RawMapLayer } from "../base";
import { toFrontLayer } from "../base";
import { DEFAULT_BASEMAP } from "../../map/basemaps";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

type LayersMethods = Pick<
  ItemClient,
  | "createMapItem"
  | "getMapConfig"
  | "saveMapConfig"
  | "listLayerSources"
  | "listFeatureLayers"
  | "sampleCollectionField"
  | "uploadMapIcon"
  | "listMapIcons"
  | "deleteMapIcon"
  | "fetchMapIconBlob"
>;

export function createLayersMethods(base: ItemClientBase): LayersMethods {
  const {
    request,
    coreUrl,
    getToken,
    fetchCoreCollections,
    fetchExternalRasterSources,
    fetchHostedTileset3dSources,
  } = base;
  return {
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
      // Multipart, patron copié de uploadThumbnail : `request()` sérialise en
      // JSON, donc fetch direct. On ne pose PAS Content-Type à la main — la
      // plateforme ajoute le boundary.
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
  };
}
