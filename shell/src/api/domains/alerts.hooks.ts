// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { AlertRulePayload } from "../types";

export function useAlertRulesForDataset(datasetItemId: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["alert-rules", datasetItemId],
    queryFn: () => client.listAlertRulesForDataset(datasetItemId),
    enabled: options?.enabled ?? true,
  });
}

export function useAlertEvaluations(
  alertItemId: string,
  options?: { enabled?: boolean; limit?: number; offset?: number },
) {
  const client = useItemClientInternal();
  return useQuery({
    // SP-50 documentait ce manque côté shell (jamais corrigé) : GET
    // /alerts/{id}/evaluations pagine déjà côté cœur (limit/offset).
    // limit/offset entrent dans la clé pour qu'un futur "Charger plus" ne
    // resserve pas le cache d'une page précédente.
    //
    // AlertRuleEditor.tsx (seul consommateur actuel de ce hook) est hors
    // périmètre du correctif shell qui a ajouté ce paramètre (exclusion
    // explicite du plan) : la fonction API et ce hook relaient bien
    // limit/offset, mais aucun contrôle "Charger plus" n'a pu être câblé
    // dans l'écran sans toucher ce fichier. Documenté, pas corrigé.
    queryKey: ["alert-evaluations", alertItemId, options?.limit, options?.offset],
    queryFn: () =>
      client.getAlertEvaluations(alertItemId, {
        limit: options?.limit,
        offset: options?.offset,
      }),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateAlertRule() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; alert: AlertRulePayload }) =>
      client.createAlertRuleItem(input),
    onSuccess: (_item, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["alert-rules", variables.alert.datasetItemId],
      });
    },
  });
}
