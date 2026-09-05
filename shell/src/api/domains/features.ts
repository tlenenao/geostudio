// SPDX-License-Identifier: Apache-2.0
import type { CollectionAdmin, FieldError, GeoJSONFeatureInput, ItemClient } from "../types";
import type { ItemClientBase } from "../base";
import { FeatureValidationError } from "../base";

async function requestFeatureWrite<T>(
  url: string,
  method: string,
  token: string | undefined,
  body?: GeoJSONFeatureInput,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { errors?: FieldError[] } | null;
    throw new FeatureValidationError(data?.errors ?? []);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : `Request failed: ${res.status} ${method} ${url}`;
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

type FeaturesMethods = Pick<
  ItemClient,
  "getCollection" | "getCollectionPermission" | "createFeature" | "updateFeature" | "deleteFeature"
>;

export function createFeaturesMethods(base: ItemClientBase): FeaturesMethods {
  const { request, coreUrl, getToken } = base;
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
        `${coreUrl}/collections/${collectionId}/items`,
        "POST",
        getToken(),
        feature,
      );
    },

    async updateFeature(
      collectionId: string,
      fid: string,
      feature: GeoJSONFeatureInput,
    ): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "PUT",
        getToken(),
        feature,
      );
    },

    async deleteFeature(collectionId: string, fid: string): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "DELETE",
        getToken(),
      );
    },
  };
}
