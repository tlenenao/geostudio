// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { MapConfig } from "../types";

export function useLayerSources(options?: { enabled?: boolean; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["layer-sources", options?.q ?? ""],
    queryFn: () => client.listLayerSources({ q: options?.q }),
    enabled: options?.enabled ?? true,
  });
}

export function useFeatureLayers(options?: { enabled?: boolean; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["feature-layers", options?.q ?? ""],
    queryFn: () => client.listFeatureLayers({ q: options?.q }),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateMap() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string }) => client.createMapItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useMapConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["map", pk],
    queryFn: () => client.getMapConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveMap(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: MapConfig) => client.saveMapConfig(pk, config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["map", pk] });
    },
  });
}
