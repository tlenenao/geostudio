// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { AdminToolName, HarvestSourceCreateInput, HarvestSourcePatchInput } from "../types";

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
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      client.setExtensionEnabled(id, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["extensions"] });
    },
  });
}

export function useLaunchAdminTool() {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (tool: AdminToolName) => client.launchAdminTool(tool),
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
      void queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useUpdateHarvestSource(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: HarvestSourcePatchInput) => client.updateHarvestSource(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useDeleteHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteHarvestSource(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useRunHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.runHarvestSource(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}
