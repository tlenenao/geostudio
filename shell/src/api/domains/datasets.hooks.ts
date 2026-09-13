// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { CreateDatasetInput, DatasetConfig } from "../types";

// GAP-22 : `getCollectionSchema` (client.getCollectionSchema, ce même
// domaine) est déjà consommé par plusieurs pages via un `useQuery` en
// ligne (DatasetEditPage, LayersPanel, VisualQueryWizardPage…) sans hook
// partagé — EditCollectionPanel (Champs sensibles) en a besoin pour
// réutiliser la même donnée que si elle affichait un futur éditeur de
// pièces jointes basé sur le schéma réel ; posé ici comme premier hook
// partagé plutôt que dupliquer un `useQuery` en ligne de plus.
export function useCollectionSchema(collectionId: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    enabled: options?.enabled ?? true,
  });
}

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
