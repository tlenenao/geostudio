// SPDX-License-Identifier: Apache-2.0
import type { ApiKeyCreated, ApiKeySummary, ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type ApiKeysMethods = Pick<ItemClient, "listApiKeys" | "createApiKey" | "revokeApiKey">;

export function createApiKeysMethods(base: ItemClientBase): ApiKeysMethods {
  const { request } = base;
  return {
    async listApiKeys(): Promise<ApiKeySummary[]> {
      return request<ApiKeySummary[]>("GET", "/api-keys");
    },

    async createApiKey(params: { name: string; expiresInDays: number }): Promise<ApiKeyCreated> {
      return request<ApiKeyCreated>("POST", "/api-keys", params);
    },

    async revokeApiKey(id: string): Promise<ApiKeySummary> {
      return request<ApiKeySummary>("DELETE", `/api-keys/${encodeURIComponent(id)}`);
    },
  };
}
