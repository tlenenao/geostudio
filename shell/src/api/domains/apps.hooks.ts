// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { AppConfig } from "../types";

export function useAppConfig(pk: string, options?: { enabled?: boolean; mode?: "runtime" }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["app", pk, options?.mode],
    queryFn: () => client.getAppConfig(pk, options?.mode),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveApp(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: AppConfig) => client.saveAppConfig(pk, config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app", pk] });
    },
  });
}
