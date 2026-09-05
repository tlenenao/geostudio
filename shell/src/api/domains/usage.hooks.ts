// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

export function useUsageTasks(params: { page: number; pageSize: number; actorId?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["usage", "tasks", params],
    queryFn: () => client.listUsageTasks(params),
  });
}

export function useUsageSummary(
  params: { since?: string; until?: string; limit?: number } = {},
  options: { enabled?: boolean } = {},
) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["usage", "summary", params],
    queryFn: () => client.getUsageSummary(params),
    enabled: options.enabled ?? true,
  });
}
