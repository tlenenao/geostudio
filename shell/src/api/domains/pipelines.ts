// SPDX-License-Identifier: Apache-2.0
import type {
  Item,
  ItemClient,
  PipelineOpsCatalog,
  PipelinePayload,
  PipelineRun,
  PipelineWebhookToken,
} from "../types";
import type { ItemClientBase } from "../base";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

type PipelinesMethods = Pick<
  ItemClient,
  | "createPipelineItem"
  | "getPipelineConfig"
  | "savePipelineConfig"
  | "getPipelineOps"
  | "runPipeline"
  | "getPipelineRuns"
  | "previewPipeline"
  | "listPipelineWebhookTokens"
  | "createPipelineWebhookToken"
  | "revokePipelineWebhookToken"
>;

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
      const data = await request<{ config?: { pipeline?: PipelinePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.pipeline)
        throw new Error("getPipelineConfig: config has no pipeline payload");
      return data.config.pipeline;
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: "pipeline",
        pipeline: payload,
      });
    },

    async getPipelineOps(): Promise<PipelineOpsCatalog> {
      return request<PipelineOpsCatalog>("GET", "/pipelines/ops");
    },

    async runPipeline(pk: string): Promise<{ runId: string }> {
      return request<{ runId: string }>("POST", `/pipelines/${pk}/run`);
    },

    async getPipelineRuns(pk: string): Promise<PipelineRun[]> {
      return request<PipelineRun[]>("GET", `/pipelines/${pk}/runs`);
    },

    async previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]> {
      return request<Record<string, unknown>[]>(
        "POST",
        `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
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
