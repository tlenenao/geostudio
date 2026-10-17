// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { ImpactTarget } from "../types";

/** Vue d'impact (ARC4-F15) ; toujours rafraîchie à l'ouverture d'un dialogue de suppression. */
export function useImpact(target: ImpactTarget | null) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["impact", target?.type, target?.id],
    queryFn: () => client.getImpact(target as ImpactTarget),
    enabled: target !== null,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });
}

/** AUD-086 : lignée amont/aval d'un item. */
export function useLineage(itemId: string) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["lineage", itemId],
    queryFn: () => client.getLineage(itemId),
    retry: false,
  });
}
