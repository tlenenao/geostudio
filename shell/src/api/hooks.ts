import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "./ItemClientProvider";
import type { ListItemsParams } from "./types";

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
