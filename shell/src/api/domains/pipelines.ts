// SPDX-License-Identifier: Apache-2.0
import type {
  Item,
  ItemClient,
  PageParams,
  PipelineOpsCatalog,
  PipelinePayload,
  PipelineRun,
  PipelineWebhookToken,
} from "../types";
import type { ItemClientBase } from "../base";
import { OWNER_PERMISSIONS } from "../../auth/permissions";
import { ifMatchHeader } from "../ifMatch";

type PipelinesMethods = Pick<
  ItemClient,
  | "createPipelineItem"
  | "getPipelineConfig"
  | "savePipelineConfig"
  | "getPipelineOps"
  | "getPipelineNextRun"
  | "runPipeline"
  | "getPipelineRuns"
  | "cancelPipelineRun"
  | "retryPipelineRun"
  | "previewPipeline"
  | "listPipelineWebhookTokens"
  | "createPipelineWebhookToken"
  | "revokePipelineWebhookToken"
>;

// `baseVersion` est un détail de transport (If-Match) : jamais dans un corps.
function withoutBaseVersion(payload: PipelinePayload): PipelinePayload {
  const rest = { ...payload };
  delete rest.baseVersion;
  return rest;
}

export function createPipelinesMethods(base: ItemClientBase): PipelinesMethods {
  const { request } = base;
  return {
    async createPipelineItem(input: {
      title: string;
      owner: string;
      pipeline: PipelinePayload;
    }): Promise<Item> {
      const config = { version: 1, kind: "pipeline", pipeline: input.pipeline };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST",
        `/configs`,
        { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createPipelineItem: core returned no itemId");
      return {
        pk: String(data.itemId),
        resourceType: "pipeline",
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

    async getPipelineConfig(pk: string): Promise<PipelinePayload> {
      const data = await request<{ version?: number; config?: { pipeline?: PipelinePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.pipeline)
        throw new Error("getPipelineConfig: config has no pipeline payload");
      return { ...data.config.pipeline, baseVersion: data.version };
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<number | undefined> {
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "pipeline", pipeline: withoutBaseVersion(payload) },
        undefined,
        ifMatchHeader(payload.baseVersion),
      );
      return saved?.version;
    },

    async getPipelineOps(): Promise<PipelineOpsCatalog> {
      return request<PipelineOpsCatalog>("GET", "/pipelines/ops");
    },

    async getPipelineNextRun(cron: string): Promise<{ nextRun: string }> {
      return request<{ nextRun: string }>(
        "GET",
        `/pipelines/next-run?cron=${encodeURIComponent(cron)}`,
      );
    },

    async runPipeline(pk: string, params?: Record<string, unknown>): Promise<{ runId: string }> {
      return request<{ runId: string }>(
        "POST",
        `/pipelines/${pk}/run`,
        params && Object.keys(params).length > 0 ? { params } : undefined,
      );
    },

    async retryPipelineRun(
      runId: string,
      opts?: { fromStart?: boolean },
    ): Promise<{ runId: string }> {
      return request<{ runId: string }>("POST", `/pipelines/runs/${runId}/retry`, {
        fromStart: opts?.fromStart ?? false,
      });
    },

    async getPipelineRuns(pk: string, params?: PageParams): Promise<PipelineRun[]> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      return request<PipelineRun[]>("GET", `/pipelines/${pk}/runs${qs ? `?${qs}` : ""}`);
    },

    async cancelPipelineRun(pk: string, runId: string): Promise<PipelineRun> {
      return request<PipelineRun>("POST", `/pipelines/${pk}/runs/${runId}/cancel`);
    },

    async previewPipeline(
      pk: string | null,
      upToNodeId: string,
      draft?: PipelinePayload,
    ): Promise<Record<string, unknown>[]> {
      // AUD-009 : un brouillon jamais enregistré (pas d'item) a sa propre route.
      const path = pk === null ? "/pipelines/preview" : `/pipelines/${pk}/preview`;
      return request<Record<string, unknown>[]>(
        "POST",
        `${path}?upTo=${encodeURIComponent(upToNodeId)}`,
        draft !== undefined ? { pipeline: withoutBaseVersion(draft) } : undefined,
      );
    },

    async listPipelineWebhookTokens(pk: string): Promise<PipelineWebhookToken[]> {
      return request<PipelineWebhookToken[]>("GET", `/pipelines/${pk}/webhook-tokens`);
    },

    async createPipelineWebhookToken(
      pk: string,
    ): Promise<{ id: string; token: string; createdAt: string }> {
      return request<{ id: string; token: string; createdAt: string }>(
        "POST",
        `/pipelines/${pk}/webhook-tokens`,
      );
    },

    async revokePipelineWebhookToken(pk: string, tokenId: string): Promise<void> {
      await request<void>("DELETE", `/pipelines/${pk}/webhook-tokens/${tokenId}`);
    },
  };
}
