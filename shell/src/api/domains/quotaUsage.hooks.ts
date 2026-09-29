// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

export function useQuotaUsage(options: { enabled?: boolean } = {}) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["quota-usage"],
    queryFn: () => client.getQuotaUsage(),
    enabled: options.enabled ?? true,
  });
}
