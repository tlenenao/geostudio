// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "./ItemClientProvider";
import type { AppConfig, CollectionCreateInput, CollectionPatchInput, CreateBookmarkInput, CreateDatasetInput, CreateKind, DatasetConfig, HarvestSourceCreateInput, HarvestSourcePatchInput, Item, ItemPage, ListItemsParams, MapConfig, Sharing, UpdatePatch } from "./types";

export { useItemClient } from "./ItemClientProvider";

export function useItems(params: ListItemsParams, opts?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["items", params],
    queryFn: () => client.listItems(params),
    enabled: opts?.enabled ?? true,
  });
}

export function useItem(pk: string) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
  });
}

export function useMe() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["me"], queryFn: () => client.getMe() });
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
    queryFn: () => client.getInstanceInfo?.() ?? Promise.resolve({ readOnly: false }),
  });
}

export function useCreateItem() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { kind: CreateKind; title: string; owner: string; templateId?: string; slug?: string }) =>
      client.createConfigItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
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
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
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
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUploadThumbnail(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => client.uploadThumbnail(pk, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
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
      queryClient.invalidateQueries({ queryKey: ["sharing", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

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
      queryClient.invalidateQueries({ queryKey: ["items"] });
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
      queryClient.invalidateQueries({ queryKey: ["map", pk] });
    },
  });
}

export function useCreateDataset() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDatasetInput) => client.createDatasetItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useCreateBookmark() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookmarkInput) => client.createBookmarkItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
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
      queryClient.invalidateQueries({ queryKey: ["dataset", pk] });
    },
  });
}

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
      queryClient.invalidateQueries({ queryKey: ["app", pk] });
    },
  });
}

export function useActiveExtensions() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["extensions"],
    // Optionnel : un ItemClient de test qui n'implémente pas encore la
    // méthode (mocks existants de AppBuilderPage.test.tsx/AppRuntimePage.test.tsx,
    // Partial<ItemClient>) résout silencieusement à [] plutôt que de faire
    // planter la query — CoreItemClient réel l'implémente toujours.
    queryFn: () => client.listActiveExtensions?.() ?? Promise.resolve([]),
  });
}

export function useAllExtensions(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["extensions", "all"],
    // Même garde défensive que useActiveExtensions ci-dessus, pour les mêmes
    // mocks de test (Partial<ItemClient>).
    queryFn: () => client.listAllExtensions?.() ?? Promise.resolve([]),
    enabled: options?.enabled ?? true,
  });
}

export function useSetExtensionEnabled() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => client.setExtensionEnabled(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["extensions"] });
    },
  });
}

export function useCollectionsAdmin(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collections", "admin"],
    queryFn: () => client.listCollections(),
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
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useUpdateCollection(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: CollectionPatchInput) => client.updateCollection(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
    },
  });
}

export function useDeleteCollection() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteCollection(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useHarvestSources(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["harvest-sources"],
    queryFn: () => client.listHarvestSources(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: HarvestSourceCreateInput) => client.createHarvestSource(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useUpdateHarvestSource(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: HarvestSourcePatchInput) => client.updateHarvestSource(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useDeleteHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteHarvestSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useRunHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.runHarvestSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
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
      queryClient.invalidateQueries({ queryKey: ["collection-sharing", id] });
    },
  });
}
