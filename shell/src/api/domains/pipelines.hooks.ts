// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
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
  return useMutation({
    mutationFn: (input: { title: string; owner: string; pipeline: PipelinePayload }) =>
      client.createPipelineItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useSavePipeline(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PipelinePayload) => client.savePipelineConfig(pk, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline", pk] });
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

export function usePipelinePreview(pipelineId: string, nodeId: string | null) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-preview", pipelineId, nodeId],
    queryFn: () => client.previewPipeline(pipelineId, nodeId!),
    enabled: nodeId !== null,
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
  return useMutation({
    mutationFn: () => client.createPipelineWebhookToken(pk),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] });
    },
  });
}

export function useRevokePipelineWebhookToken(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tokenId: string) => client.revokePipelineWebhookToken(pk, tokenId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] });
    },
  });
}
