// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { CreateDatasetInput, DatasetConfig } from "../types";

export function useCreateDataset() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDatasetInput) => client.createDatasetItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useDatasetConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["dataset", pk],
    queryFn: () => client.getDatasetConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveDataset(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: DatasetConfig) => client.saveDatasetConfig(pk, config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dataset", pk] });
    },
  });
}
