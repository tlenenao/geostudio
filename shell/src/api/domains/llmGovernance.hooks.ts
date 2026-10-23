// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient } from "../ItemClientProvider";
import type { LlmSettingsWrite } from "../types";

export function useLlmUsage() {
  const client = useItemClient();
  return useQuery({ queryKey: ["llm-usage"], queryFn: () => client.getLlmUsage() });
}

export function useLlmSettings() {
  const client = useItemClient();
  return useQuery({ queryKey: ["llm-settings"], queryFn: () => client.getLlmSettings() });
}

export function useSaveLlmSettings() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LlmSettingsWrite) => client.putLlmSettings(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["llm-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
  });
}

export function useDeleteLlmSettings() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => client.deleteLlmSettings(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["llm-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
  });
}
