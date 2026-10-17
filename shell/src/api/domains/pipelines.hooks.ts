// SPDX-License-Identifier: Apache-2.0
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import { useToast } from "../../ui/kit/ToastProvider";
import { t } from "../../i18n";
import type { PipelinePayload } from "../types";

export function usePipelineConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline", pk],
    queryFn: () => client.getPipelineConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useCreatePipeline() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; pipeline: PipelinePayload }) =>
      client.createPipelineItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      showToast(t("toast.pipelineCreated"));
    },
  });
}

export function useSavePipeline(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (payload: PipelinePayload) => client.savePipelineConfig(pk, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline", pk] });
      showToast(t("toast.pipelineSaved"));
    },
  });
}

export function usePipelineOps() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-ops"],
    queryFn: () => client.getPipelineOps(),
    staleTime: Infinity, // catalogue statique côté serveur, jamais invalidé
  });
}

export function usePipelineNextRun(cron: string, enabled: boolean) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-next-run", cron],
    queryFn: () => client.getPipelineNextRun(cron),
    enabled,
  });
}

// AUD-008 : la clé d'aperçu ne dépend que de ce qui change le résultat — jamais des
// positions (chaque frame de drag relançait l'aperçu côté serveur), titres ou notes.
export function previewDraftKey(draft: PipelinePayload | undefined): string {
  if (!draft) return "";
  return JSON.stringify({
    nodes: draft.nodes.map(({ id, kind, op, params }) => ({ id, kind, op, params })),
    edges: draft.edges,
    parameters: draft.parameters ?? null,
  });
}

export function usePipelinePreview(
  pipelineId: string | null,
  nodeId: string | null,
  draft?: PipelinePayload,
) {
  const client = useItemClientInternal();
  const key = previewDraftKey(draft);
  const [debouncedKey, setDebouncedKey] = useState(key);
  useEffect(() => {
    const id = setTimeout(() => setDebouncedKey(key), 400);
    return () => clearTimeout(id);
  }, [key]);
  return useQuery({
    queryKey: ["pipeline-preview", pipelineId, nodeId, debouncedKey],
    queryFn: () => client.previewPipeline(pipelineId, nodeId!, draft),
    enabled: nodeId !== null && (pipelineId !== null || draft !== undefined),
    placeholderData: keepPreviousData,
  });
}

export function usePipelineWebhookTokens(pk: string) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-webhook-tokens", pk],
    queryFn: () => client.listPipelineWebhookTokens(pk),
  });
}

export function useCreatePipelineWebhookToken(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => client.createPipelineWebhookToken(pk),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] });
      showToast(t("toast.webhookTokenCreated"));
    },
  });
}

export function useRevokePipelineWebhookToken(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (tokenId: string) => client.revokePipelineWebhookToken(pk, tokenId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] });
      showToast(t("toast.webhookTokenRevoked"));
    },
  });
}
