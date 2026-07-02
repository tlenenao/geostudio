import type { CreateKind, Group, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, ResourceType, Sharing, UpdatePatch } from "./types";
import { DEFAULT_BASEMAP } from "../map/basemaps";

type GeoNodeResource = {
  pk: number | string;
  resource_type: string;
  title: string;
  abstract?: string;
  owner?: { username?: string };
  thumbnail_url?: string | null;
  date?: string;
};

function toItem(r: GeoNodeResource): Item {
  return {
    pk: String(r.pk),
    resourceType: (r.resource_type as ResourceType) ?? "map",
    title: r.title,
    abstract: r.abstract ?? "",
    owner: r.owner?.username ?? "",
    thumbnailUrl: r.thumbnail_url ?? null,
    date: r.date ?? "",
    configId: null,
  };
}

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

export function createItemClient(opts: {
  geonodeUrl: string;
  builderUrl: string;
  martinUrl?: string;
  featureservUrl?: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { geonodeUrl, builderUrl, martinUrl, featureservUrl, getToken } = opts;

  async function get<T>(path: string): Promise<T> {
    const token = getToken();
    const res = await fetch(`${geonodeUrl}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${path}`);
    }
    return (await res.json()) as T;
  }

  async function fetchMartinSources(): Promise<LayerSource[]> {
    if (!martinUrl) return [];
    const res = await fetch(`${martinUrl}/catalog`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /catalog`);
    const data = (await res.json()) as {
      tiles?: Record<string, { description?: string }>;
    };
    return Object.entries(data.tiles ?? {}).map(([id, meta]) => ({
      id,
      title: meta.description ?? id,
      service: "martin" as const,
      kind: "vector" as const,
      tilesUrl: `${martinUrl}/${id}/{z}/{x}/{y}`,
      sourceLayer: id,
    }));
  }

  async function fetchFeatureservSources(): Promise<LayerSource[]> {
    if (!featureservUrl) return [];
    const res = await fetch(`${featureservUrl}/collections.json`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections.json`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "featureserv" as const,
      kind: "feature" as const,
      url: `${featureservUrl}/collections/${c.id}/items.json`,
    }));
  }

  return {
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("search", params.q);
      if (params.type) q.set("filter{resource_type.in}", params.type);
      if (params.scope === "mine" && params.me) {
        q.set("filter{owner.username.in}", params.me);
      }
      if (params.scope === "public") {
        q.set("filter{is_published}", "true");
      }
      q.set("page", String(params.page ?? 1));
      q.set("page_size", String(params.pageSize ?? 12));
      const data = await get<{
        total: number;
        page: number;
        page_size: number;
        resources: GeoNodeResource[];
      }>(`/api/v2/resources?${q.toString()}`);
      let items = data.resources.map(toItem);
      let total = data.total;
      if (params.scope === "shared" && params.me) {
        // Page-local exclusion of owned items (GeoNode has no "shared with me"
        // param). `total` is only corrected for this page, so multi-page totals
        // are approximate — documented limitation. Never let it go negative.
        const before = items.length;
        items = items.filter((i) => i.owner !== params.me);
        total = Math.max(0, total - (before - items.length));
      }
      return { items, total, page: data.page, pageSize: data.page_size };
    },

    async getItem(pk: string): Promise<Item> {
      const data = await get<{ resource: GeoNodeResource }>(`/api/v2/resources/${pk}`);
      return toItem(data.resource);
    },

    async getMe(): Promise<Me> {
      const data = await get<{
        user: { username: string; first_name?: string; last_name?: string };
      }>(`/api/v2/users/me`);
      return {
        username: data.user.username,
        firstName: data.user.first_name ?? "",
        lastName: data.user.last_name ?? "",
      };
    },

    async createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item> {
      const config = {
        version: 1,
        kind: input.kind,
        theme: {},
        dataSources: [],
        layout: { type: "grid", breakpoints: {}, items: [] },
        messages: [],
      };
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ title: input.title, owner: input.owner, config }),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} /configs`);
      }
      const data = (await res.json()) as {
        id: string | number;
        kind: string;
        itemId: string | null;
      };
      if (!data.itemId) {
        throw new Error("createConfigItem: builder returned no itemId");
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
      };
    },

    async updateItem(pk: string, patch: UpdatePatch): Promise<Item> {
      const token = getToken();
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PATCH /resources/${pk}`);
      }
      const data = (await res.json()) as { resource: GeoNodeResource };
      return toItem(data.resource);
    },

    async uploadThumbnail(pk: string, file: File): Promise<void> {
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}/set_thumbnail`, {
        method: "PUT",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PUT thumbnail`);
      }
    },

    async deleteItem(pk: string): Promise<void> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(`Request failed: ${res.status} DELETE /configs/by-item/${pk}`);
      }
    },

    async listGroups(): Promise<Group[]> {
      const data = await get<{ group_profiles: { pk: number | string; title: string }[] }>(
        `/api/v2/groups`,
      );
      return data.group_profiles.map((g) => ({ id: String(g.pk), title: g.title }));
    },

    async getSharing(pk: string): Promise<Sharing> {
      const data = await get<{ groups: { id: string; permissions: string }[] }>(
        `/api/v2/resources/${pk}/permissions`,
      );
      return {
        public: data.groups.some((g) => g.id === "anonymous"),
        groups: data.groups
          .filter((g) => g.id !== "anonymous")
          .map((g) => ({ groupId: g.id, role: g.permissions === "edit" ? "editor" : "viewer" })),
      };
    },

    async setSharing(pk: string, sharing: Sharing): Promise<void> {
      const token = getToken();
      const groups = [
        ...(sharing.public ? [{ id: "anonymous", permissions: "view" }] : []),
        ...sharing.groups.map((g) => ({
          id: g.groupId,
          permissions: g.role === "editor" ? "edit" : "view",
        })),
      ];
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}/permissions`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ groups }),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PUT permissions`);
      }
    },

    async listLayerSources(): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(),
        fetchFeatureservSources(),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },

    async createMapItem(input: { title: string; owner: string }): Promise<Item> {
      const map: MapConfig = {
        basemap: { style: DEFAULT_BASEMAP.style },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
      const config = { version: 1, kind: "map", map };
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ title: input.title, owner: input.owner, config }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /configs`);
      const data = (await res.json()) as { id: string | number; kind: string; itemId: string | null };
      if (!data.itemId) throw new Error("createMapItem: builder returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "map", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
      };
    },

    async getMapConfig(pk: string): Promise<MapConfig> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} GET /configs/by-item/${pk}`);
      // ConfigRead nests the builder config under "config"; the map is config.map.
      const data = (await res.json()) as {
        config?: { map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null };
      };
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
      };
    },

    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ version: 1, kind: "map", map: config }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} PUT /configs/by-item/${pk}`);
    },
  };
}
