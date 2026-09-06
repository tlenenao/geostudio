// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type {
  CreateBookmarkInput,
  CreateKind,
  Item,
  ItemFacets,
  ItemPage,
  ListItemsParams,
  Sharing,
  UpdatePatch,
} from "../types";

export function useItems(params: ListItemsParams, opts?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["items", params],
    queryFn: () => client.listItems(params),
    enabled: opts?.enabled ?? true,
  });
}

export function useItemFacets(
  params: Pick<ListItemsParams, "q" | "type" | "scope" | "owner">,
  opts?: { enabled?: boolean },
) {
  const client = useItemClientInternal();
  return useQuery<ItemFacets>({
    queryKey: ["item-facets", params],
    queryFn: () => client.getItemFacets(params),
    enabled: opts?.enabled ?? true,
  });
}

export function useItem(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useInstanceInfo() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["instance"],
    // Garde défensive identique à useActiveExtensions ci-dessous : un
    // ItemClient de test qui n'implémente pas encore la méthode (mocks
    // Partial<ItemClient>) résout silencieusement à { readOnly: false }
    // plutôt que de planter la query. Une vraie panne réseau laisse `data`
    // undefined (react-query), et chaque appelant traite ça en fail-open
    // via `?.readOnly === true` — jamais un faux positif "lecture seule".
    // Même garde défensive pour etlEnabled que pour readOnly ci-dessus
    // (SP-15b) : un ItemClient de test qui ne l'implémente pas encore
    // résout silencieusement à false plutôt que de planter la query.
    queryFn: () =>
      client.getInstanceInfo?.() ??
      Promise.resolve({ readOnly: false, etlEnabled: false, exportEnabled: false }),
  });
}

export function useCreateItem() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      kind: CreateKind;
      title: string;
      owner: string;
      templateId?: string;
      slug?: string;
    }) => client.createConfigItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useDeleteItem() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pk: string) => client.deleteItem(pk),
    onMutate: async (pk: string) => {
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const previous = queryClient.getQueriesData<ItemPage>({ queryKey: ["items"] });
      queryClient.setQueriesData<ItemPage>({ queryKey: ["items"] }, (old) => {
        if (!old) return old;
        const items = old.items.filter((i) => i.pk !== pk);
        // Only decrement total on the page that actually contained the item.
        const removed = old.items.length - items.length;
        return { ...old, items, total: old.total - removed };
      });
      return { previous };
    },
    onError: (_err, _pk, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: (_data, _err, pk) => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      void queryClient.invalidateQueries({ queryKey: ["item", pk] });
    },
  });
}

export function useUpdateItem(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: UpdatePatch) => client.updateItem(pk, patch),
    onMutate: async (patch: UpdatePatch) => {
      await queryClient.cancelQueries({ queryKey: ["item", pk] });
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const prevItem = queryClient.getQueryData<Item>(["item", pk]);
      const prevLists = queryClient.getQueriesData<ItemPage>({ queryKey: ["items"] });
      const merge = (i: Item): Item => ({
        ...i,
        ...(patch.title !== undefined ? { title: patch.title } : {}),
        ...(patch.abstract !== undefined ? { abstract: patch.abstract } : {}),
      });
      queryClient.setQueryData<Item>(["item", pk], (old) => (old ? merge(old) : old));
      queryClient.setQueriesData<ItemPage>({ queryKey: ["items"] }, (old) =>
        old ? { ...old, items: old.items.map((i) => (i.pk === pk ? merge(i) : i)) } : old,
      );
      return { prevItem, prevLists };
    },
    onError: (_err, _patch, ctx) => {
      if (ctx) {
        queryClient.setQueryData(["item", pk], ctx.prevItem);
        ctx.prevLists.forEach(([key, data]) => queryClient.setQueryData(key, data));
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["item", pk] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUploadThumbnail(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => client.uploadThumbnail(pk, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["item", pk] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useGroups(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["groups"],
    queryFn: () => client.listGroups(),
    enabled: options?.enabled ?? true,
  });
}

export function useSharing(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["sharing", pk],
    queryFn: () => client.getSharing(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSetSharing(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sharing: Sharing) => client.setSharing(pk, sharing),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sharing", pk] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useCreateBookmark() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookmarkInput) => client.createBookmarkItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useMetadataCatalog() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["metadata-catalog"],
    queryFn: () => client.getMetadataCatalog(),
    staleTime: Infinity, // catalogue statique côté cœur, jamais invalidé
  });
}
