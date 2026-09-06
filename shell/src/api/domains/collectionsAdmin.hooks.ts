// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { CollectionCreateInput, CollectionPatchInput, Sharing } from "../types";

export function useCollectionsAdmin(options?: { q?: string; enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collections", "admin", options?.q ?? ""],
    queryFn: () => client.listCollections(options?.q ? { q: options.q } : undefined),
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
