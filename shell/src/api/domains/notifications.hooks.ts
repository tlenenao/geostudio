// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { ItemClient, NotificationPreferenceValue } from "../types";

export function useNotifications(params: { page: number; pageSize: number }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => client.listNotifications(params),
    placeholderData: keepPreviousData, // « Charger plus » : pas de flash de liste vide
  });
}

const UNREAD_KEY = ["notifications", "unread-count"];

// L13/D7 : le flux SSE pousse le compte ; le sondage de 45 s ci-dessous reste le
// repli (flux refusé, coupé par un proxy, plafond de connexions atteint). Le
// cœur ferme le flux après ~55 s : on se reconnecte, avec attente croissante
// après une erreur.
export async function runNotificationStream(
  client: Pick<ItemClient, "subscribeNotifications">,
  queryClient: QueryClient,
  signal: AbortSignal,
  wait: (ms: number) => Promise<void> = (ms) =>
    new Promise((resolve) => {
      setTimeout(resolve, ms);
    }),
): Promise<void> {
  let failures = 0;
  while (!signal.aborted) {
    try {
      await client.subscribeNotifications((count) => {
        failures = 0;
        if (queryClient.getQueryData(UNREAD_KEY) === count) return;
        queryClient.setQueryData(UNREAD_KEY, count);
        void queryClient.invalidateQueries({
          queryKey: ["notifications"],
          predicate: (q) => q.queryKey[1] !== "unread-count",
        });
      }, signal);
      await wait(1_000);
    } catch {
      if (signal.aborted) return;
      failures += 1;
      await wait(Math.min(5_000 * 2 ** failures, 60_000));
    }
  }
}

export function useUnreadNotificationCount() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  useEffect(() => {
    const controller = new AbortController();
    void runNotificationStream(client, queryClient, controller.signal);
    return () => {
      controller.abort();
    };
  }, [client, queryClient]);
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => client.getUnreadNotificationCount(),
    refetchInterval: 45_000,
    // Sondage indéfini global (monté une fois dans TopBar, toute la session),
    // pas le patron "boucle manuelle capped" de PipelineRunPanel/ExportPanel/
    // ImportFileButton (poll jusqu'à fin d'UN job précis, plafonné) — forme de
    // problème différente, refetchInterval react-query est le bon outil ici.
  });
}

export function useMarkNotificationRead() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.markNotificationRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => client.markAllNotificationsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useNotificationPreference() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", "preference"],
    queryFn: () => client.getNotificationPreference(),
  });
}

export function useUpdateNotificationPreference() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: NotificationPreferenceValue) => client.updateNotificationPreference(value),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
