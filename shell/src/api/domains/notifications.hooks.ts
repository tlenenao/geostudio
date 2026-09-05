// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { NotificationPreferenceValue } from "../types";

export function useNotifications(params: { page: number; pageSize: number }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => client.listNotifications(params),
  });
}

export function useUnreadNotificationCount() {
  const client = useItemClientInternal();
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
