// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, QuotaUsage } from "../types";
import type { ItemClientBase } from "../base";

type QuotaUsageMethods = Pick<ItemClient, "getQuotaUsage">;

export function createQuotaUsageMethods(base: ItemClientBase): QuotaUsageMethods {
  const { request } = base;
  return {
    async getQuotaUsage(): Promise<QuotaUsage> {
      return request<QuotaUsage>("GET", "/admin/usage");
    },
  };
}
