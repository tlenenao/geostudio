// SPDX-License-Identifier: Apache-2.0
import type { Impact, ImpactTarget, ItemClient, Lineage } from "../types";
import type { ItemClientBase } from "../base";

type ImpactMethods = Pick<ItemClient, "getImpact" | "getLineage">;

export function createImpactMethods(base: ItemClientBase): ImpactMethods {
  const { request } = base;
  return {
    async getImpact(target: ImpactTarget): Promise<Impact> {
      const root = target.type === "collection" ? "collections" : "items";
      return request<Impact>("GET", `/${root}/${encodeURIComponent(target.id)}/impact`);
    },
    async getLineage(itemId: string): Promise<Lineage> {
      return request<Lineage>("GET", `/items/${encodeURIComponent(itemId)}/lineage`);
    },
  };
}
