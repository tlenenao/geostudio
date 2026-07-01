import type { CreateKind, Group, Item, ItemClient, ItemPage, ListItemsParams, Me, ResourceType, Sharing, UpdatePatch } from "./types";

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

export function createItemClient(opts: {
  geonodeUrl: string;
  builderUrl: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { geonodeUrl, builderUrl, getToken } = opts;

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

  return {
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("search", params.q);
      if (params.type) q.set("filter{resource_type.in}", params.type);
      q.set("page", String(params.page ?? 1));
      q.set("page_size", String(params.pageSize ?? 12));
      const data = await get<{
        total: number;
        page: number;
        page_size: number;
        resources: GeoNodeResource[];
      }>(`/api/v2/resources?${q.toString()}`);
      return {
        items: data.resources.map(toItem),
        total: data.total,
        page: data.page,
        pageSize: data.page_size,
      };
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
  };
}
