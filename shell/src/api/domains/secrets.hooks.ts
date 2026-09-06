// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { SecretPayload } from "../types";

export function useListSecrets() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["secrets"], queryFn: () => client.listSecrets() });
}

export function useCreateSecret() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; payload: SecretPayload }) => client.createSecret(input),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["secrets"] }),
  });
}

export function useDeleteSecret() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteSecret(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["secrets"] }),
  });
}
