import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient } from "./ItemClientProvider";
import type { CreateKind, ListItemsParams } from "./types";

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

export function useCreateItem() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { kind: CreateKind; title: string; owner: string }) =>
      client.createConfigItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
