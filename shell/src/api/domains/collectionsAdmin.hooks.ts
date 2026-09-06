// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { CollectionCreateInput, CollectionPatchInput, Sharing } from "../types";

export function useCollectionsAdmin(options?: {
  q?: string;
  limit?: number;
  offset?: number;
  enabled?: boolean;
}) {
  const client = useItemClientInternal();
  return useQuery({
    // SP-50 documentait ce manque côté shell (jamais corrigé) : GET
    // /collections pagine déjà côté cœur (limit/offset) — limit/offset
    // entrent dans la clé pour que "Charger plus" (CollectionsAdminPage)
    // déclenche bien un nouveau fetch plutôt que de resservir le cache.
    queryKey: ["collections", "admin", options?.q ?? "", options?.limit, options?.offset],
    queryFn: () =>
      client.listCollections({
        q: options?.q,
        limit: options?.limit,
        offset: options?.offset,
      }),
    enabled: options?.enabled ?? true,
  });
}

export function useCandidateTables(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collections", "candidates"],
    queryFn: () => client.listCandidateTables(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateCollection() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CollectionCreateInput) => client.createCollection(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      void queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useUpdateCollection(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: CollectionPatchInput) => client.updateCollection(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
    },
  });
}

export function useDeleteCollection() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteCollection(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      void queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useCollectionSharing(id: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collection-sharing", id],
    queryFn: () => client.getCollectionSharing(id),
    enabled: options?.enabled ?? true,
  });
}

export function useSetCollectionSharing(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sharing: Sharing) => client.setCollectionSharing(id, sharing),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collection-sharing", id] });
    },
  });
}
