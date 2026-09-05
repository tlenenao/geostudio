// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, UsageSummary, UsageTask } from "../types";
import type { ItemClientBase } from "../base";

type UsageMethods = Pick<ItemClient, "listUsageTasks" | "getUsageSummary">;

export function createUsageMethods(base: ItemClientBase): UsageMethods {
  const { request } = base;
  return {
    async listUsageTasks(params: {
      page: number;
      pageSize: number;
      actorId?: string;
    }): Promise<{ tasks: UsageTask[]; total: number }> {
      const query = new URLSearchParams({
        page: String(params.page),
        pageSize: String(params.pageSize),
      });
      if (params.actorId) query.set("actorId", params.actorId);
      return request<{ tasks: UsageTask[]; total: number }>(
        "GET",
        `/usage/tasks?${query.toString()}`,
      );
    },

    async getUsageSummary(
      params: { since?: string; until?: string; limit?: number } = {},
    ): Promise<UsageSummary> {
      const query = new URLSearchParams();
      if (params.since) query.set("since", params.since);
      if (params.until) query.set("until", params.until);
      if (params.limit) query.set("limit", String(params.limit));
      const qs = query.toString();
      return request<UsageSummary>("GET", `/usage/summary${qs ? `?${qs}` : ""}`);
    },
  };
}
