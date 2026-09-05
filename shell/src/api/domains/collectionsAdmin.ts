// SPDX-License-Identifier: Apache-2.0
import type {
  CandidateTable,
  CollectionAdmin,
  CollectionCreateInput,
  CollectionPatchInput,
  CreateEmptyCollectionInput,
  ItemClient,
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
>;

export function createCollectionsAdminMethods(base: ItemClientBase): CollectionsAdminMethods {
  const { request } = base;
  return {
    async listCollections(): Promise<CollectionAdmin[]> {
      const data = await request<{ collections: CollectionAdmin[] }>("GET", `/collections`);
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
  };
}
