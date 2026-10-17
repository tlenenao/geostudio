// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

export function useApiKeys() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["api-keys"], queryFn: () => client.listApiKeys() });
}

export function useCreateApiKey() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { name: string; expiresInDays: number; readOnly?: boolean }) =>
      client.createApiKey(params),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
  });
}

export function useRevokeApiKey() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.revokeApiKey(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
  });
}
