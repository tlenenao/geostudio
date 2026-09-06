// SPDX-License-Identifier: Apache-2.0
import type {
  Item,
  ItemClient,
  PageParams,
  ReportRunStatus,
  ReportSchedulePayload,
} from "../types";
import type { ItemClientBase } from "../base";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

type ReportsMethods = Pick<
  ItemClient,
  | "createReportScheduleItem"
  | "getReportScheduleConfig"
  | "saveReportScheduleConfig"
  | "getReportRuns"
>;

export function createReportsMethods(base: ItemClientBase): ReportsMethods {
  const { request } = base;
  return {
    async createReportScheduleItem(input: {
      title: string;
      owner: string;
      report: ReportSchedulePayload;
    }): Promise<Item> {
      const config = { version: 1, kind: "report", report: input.report };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createReportScheduleItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: "report",
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

    async getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload> {
      const data = await request<{ config?: { report?: ReportSchedulePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.report)
        throw new Error("getReportScheduleConfig: config has no report payload");
      return data.config.report;
    },

    async saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: "report",
        report: payload,
      });
    },

    async getReportRuns(pk: string, params?: PageParams): Promise<ReportRunStatus[]> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      return request<ReportRunStatus[]>("GET", `/reports/${pk}/runs${qs ? `?${qs}` : ""}`);
    },
  };
}
