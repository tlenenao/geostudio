// SPDX-License-Identifier: Apache-2.0
import type { CollectionAdmin, GeoJSONFeatureInput, ItemClient } from "../types";
import type { ItemClientBase } from "../base";
import { FeatureValidationError, parseErrorResponse } from "../base";

async function requestFeatureWrite<T>(
  authFetch: ItemClientBase["authFetch"],
  url: string,
  method: string,
  body?: GeoJSONFeatureInput,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const res = await authFetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await parseErrorResponse(res);
    // 400 (écriture de feature) ou 422 : erreurs par champ `{field, code, message}`.
    if ((res.status === 400 || res.status === 422) && err.errors) {
      throw new FeatureValidationError(err.errors);
    }
    if (res.status === 400) throw new FeatureValidationError([]);
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

type FeaturesMethods = Pick<
  ItemClient,
  "getCollection" | "getCollectionPermission" | "createFeature" | "updateFeature" | "deleteFeature"
>;

export function createFeaturesMethods(base: ItemClientBase): FeaturesMethods {
  const { request, coreUrl, authFetch } = base;
  return {
    async getCollection(collectionId: string): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("GET", `/collections/${collectionId}`);
    },

    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ permissions?: { write?: boolean } }>(
        "GET",
        `/collections/${collectionId}`,
      );
      return data.permissions?.write ?? false;
    },

    async createFeature(
      collectionId: string,
      feature: GeoJSONFeatureInput,
    ): Promise<{ id: string | number }> {
      return requestFeatureWrite<{ id: string | number }>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items`,
        "POST",
        feature,
      );
    },

    async updateFeature(
      collectionId: string,
      fid: string,
      feature: GeoJSONFeatureInput,
    ): Promise<void> {
      await requestFeatureWrite<void>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "PUT",
        feature,
      );
    },

    async deleteFeature(collectionId: string, fid: string): Promise<void> {
      await requestFeatureWrite<void>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "DELETE",
      );
    },
  };
}
