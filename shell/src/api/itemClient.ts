import type { Item, ItemClient, ItemPage, ListItemsParams, Me, ResourceType } from "./types";

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
  const { geonodeUrl, getToken } = opts;

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
  };
}
