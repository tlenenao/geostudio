// SPDX-License-Identifier: Apache-2.0
import type {
  BookmarkPayload,
  ConfigRevisionInfo,
  CreateKind,
  CreateBookmarkInput,
  Group,
  InstanceInfo,
  Item,
  ItemClient,
  ItemPage,
  ListItemsParams,
  MetadataCatalog,
  ResourceType,
  Sharing,
  UpdatePatch,
} from "./types";
import { getTemplate } from "../builder/templates";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import {
  createBase,
  FeatureValidationError,
  SqlQueryError,
  toFrontLayer,
  type RawMapLayer,
} from "./base";
import { createAlertsMethods } from "./domains/alerts";
import { createAppsMethods } from "./domains/apps";
import { createAttachmentsMethods } from "./domains/attachments";
import { createCollectionsAdminMethods } from "./domains/collectionsAdmin";
import { createDatasetsMethods } from "./domains/datasets";
import { createExportsIngestionMethods } from "./domains/exportsIngestion";
import { createFeaturesMethods } from "./domains/features";
import { createExtensionsAdminToolsMethods } from "./domains/extensionsAdminTools";
import { createIdentityMethods } from "./domains/identity";
import { createLayersMethods } from "./domains/layers";
import { createNotificationsMethods } from "./domains/notifications";
import { createPipelinesMethods } from "./domains/pipelines";
import { createReportsMethods } from "./domains/reports";
import { createTiles3dMethods } from "./domains/tiles3d";

export { FeatureValidationError, SqlQueryError, toFrontLayer, type RawMapLayer };

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

    ...createLayersMethods(base),

    ...createExtensionsAdminToolsMethods(base),

    ...createCollectionsAdminMethods(base),

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

    ...createDatasetsMethods(base),

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

    ...createAppsMethods(base),

    ...createExportsIngestionMethods(base),

    ...createAttachmentsMethods(base),

    ...createFeaturesMethods(base),

    ...createTiles3dMethods(base),

    getAuthToken: getToken,
    getCoreUrl: () => coreUrl,
  };
}
