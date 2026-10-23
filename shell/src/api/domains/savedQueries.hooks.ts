// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

const KEY = ["saved-sql-queries"] as const;

export function useSavedSqlQueries(enabled = true) {
  const client = useItemClientInternal();
  return useQuery({ queryKey: KEY, queryFn: () => client.listSavedSqlQueries(), enabled });
}

export function useSaveSqlQuery() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; sql: string }) => client.createSavedSqlQuery(body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteSavedSqlQuery() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteSavedSqlQuery(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
