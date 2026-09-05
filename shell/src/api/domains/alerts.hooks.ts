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

export function useAlertEvaluations(alertItemId: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["alert-evaluations", alertItemId],
    queryFn: () => client.getAlertEvaluations(alertItemId),
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
