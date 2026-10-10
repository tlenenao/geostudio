// SPDX-License-Identifier: Apache-2.0
import type {
  CandidateTable,
  CollectionAdmin,
  CollectionCreateInput,
  CollectionPatchInput,
  CreateEmptyCollectionInput,
  GeoLimit,
  GeoLimitTarget,
  ItemClient,
  PageParams,
  Sharing,
} from "../types";
import type { ItemClientBase } from "../base";

type CollectionsAdminMethods = Pick<
  ItemClient,
  | "listCollections"
  | "listCandidateTables"
  | "createCollection"
  | "createEmptyCollection"
  | "updateCollection"
  | "deleteCollection"
  | "getCollectionSharing"
  | "setCollectionSharing"
  | "listGeoLimits"
  | "putGeoLimit"
  | "deleteGeoLimit"
>;

export function createCollectionsAdminMethods(base: ItemClientBase): CollectionsAdminMethods {
  const { request } = base;
  return {
    async listCollections(params?: { q?: string } & PageParams): Promise<CollectionAdmin[]> {
      const query = new URLSearchParams();
      if (params?.q) query.set("q", params.q);
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      const data = await request<{ collections: CollectionAdmin[] }>(
        "GET",
        `/collections${qs ? `?${qs}` : ""}`,
      );
      return data.collections ?? [];
    },

    async listCandidateTables(): Promise<CandidateTable[]> {
      const data = await request<{ candidates: CandidateTable[] }>(
        "GET",
        `/collections/candidates`,
      );
      return data.candidates ?? [];
    },

    async createCollection(input: CollectionCreateInput): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("POST", `/collections`, input);
    },

    async createEmptyCollection(input: CreateEmptyCollectionInput): Promise<{ id: string }> {
      const data = await request<{ id: string }>("POST", "/collections/empty", {
        title: input.title,
        columns: input.columns,
        geometryType: input.geometryType,
        srid: input.srid,
      });
      return { id: data.id };
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

    // GAP-27 : limites géographiques de lecture (admin.collections.manage).
    async listGeoLimits(collectionId: string): Promise<GeoLimit[]> {
      const data = await request<{ limits: GeoLimit[] }>(
        "GET",
        `/collections/${collectionId}/geo-limits`,
      );
      return data.limits ?? [];
    },

    async putGeoLimit(
      collectionId: string,
      targetType: GeoLimitTarget,
      targetId: string,
      geometry: Record<string, unknown>,
    ): Promise<GeoLimit> {
      return request<GeoLimit>(
        "PUT",
        `/collections/${collectionId}/geo-limits/${targetType}/${encodeURIComponent(targetId)}`,
        { geometry },
      );
    },

    async deleteGeoLimit(
      collectionId: string,
      targetType: GeoLimitTarget,
      targetId: string,
    ): Promise<void> {
      await request<void>(
        "DELETE",
        `/collections/${collectionId}/geo-limits/${targetType}/${encodeURIComponent(targetId)}`,
      );
    },
  };
}
