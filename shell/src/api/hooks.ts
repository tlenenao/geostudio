import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient } from "./ItemClientProvider";
import type { CreateKind, Item, ItemPage, ListItemsParams, UpdatePatch } from "./types";

export function useItems(params: ListItemsParams) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["items", params],
    queryFn: () => client.listItems(params),
  });
}

export function useItem(pk: string) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
  });
}

export function useMe() {
  const client = useItemClient();
  return useQuery({ queryKey: ["me"], queryFn: () => client.getMe() });
}

export function useCreateItem() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { kind: CreateKind; title: string; owner: string }) =>
      client.createConfigItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useDeleteItem() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pk: string) => client.deleteItem(pk),
    onMutate: async (pk: string) => {
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const previous = queryClient.getQueriesData<ItemPage>({ queryKey: ["items"] });
      queryClient.setQueriesData<ItemPage>({ queryKey: ["items"] }, (old) =>
        old
          ? { ...old, items: old.items.filter((i) => i.pk !== pk), total: old.total - 1 }
          : old,
      );
      return { previous };
    },
    onError: (_err, _pk, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUpdateItem(pk: string) {
  const client = useItemClient();
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
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUploadThumbnail(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => client.uploadThumbnail(pk, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
