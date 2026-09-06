// SPDX-License-Identifier: Apache-2.0
import type {
  AlertEvaluation,
  AlertRulePayload,
  AlertRuleSummary,
  Item,
  ItemClient,
  PageParams,
} from "../types";
import type { ItemClientBase } from "../base";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

type AlertsMethods = Pick<
  ItemClient,
  | "createAlertRuleItem"
  | "getAlertRuleConfig"
  | "saveAlertRuleConfig"
  | "listAlertRulesForDataset"
  | "getAlertEvaluations"
>;

export function createAlertsMethods(base: ItemClientBase): AlertsMethods {
  const { request } = base;
  return {
    async createAlertRuleItem(input: {
      title: string;
      owner: string;
      alert: AlertRulePayload;
    }): Promise<Item> {
      const config = { version: 1, kind: "alert", alert: input.alert };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createAlertRuleItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: "alert",
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

    async getAlertRuleConfig(pk: string): Promise<AlertRulePayload> {
      const data = await request<{ config?: { alert?: AlertRulePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.alert) throw new Error("getAlertRuleConfig: config has no alert payload");
      return data.config.alert;
    },

    async saveAlertRuleConfig(pk: string, payload: AlertRulePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: "alert",
        alert: payload,
      });
    },

    async listAlertRulesForDataset(datasetItemId: string): Promise<AlertRuleSummary[]> {
      return request<AlertRuleSummary[]>("GET", `/datasets/${datasetItemId}/alerts`);
    },

    async getAlertEvaluations(
      alertItemId: string,
      params?: PageParams,
    ): Promise<AlertEvaluation[]> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      return request<AlertEvaluation[]>(
        "GET",
        `/alerts/${alertItemId}/evaluations${qs ? `?${qs}` : ""}`,
      );
    },
  };
}
