// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { RoleCreateInput, RolePatchInput } from "../types";

export function useMe() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["me"], queryFn: () => client.getMe() });
}

export function useRolesCatalog() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["roles", "catalog"], queryFn: () => client.getPrivilegeCatalog() });
}

export function useRoles(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["roles"],
    queryFn: () => client.listRoles(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RoleCreateInput) => client.createRole(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useUpdateRole(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: RolePatchInput) => client.updateRole(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useDeleteRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteRole(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useUsers(params: { page: number; pageSize: number; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["users", params],
    queryFn: () => client.listUsers(params),
  });
}

export function useUpdateUserRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; roleId: string }) =>
      client.updateUserRole(vars.id, vars.roleId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      // Un admin peut changer son propre rôle depuis cette page (seule garde
      // serveur : anti-lockout sur le dernier titulaire des privilèges
      // sensibles, pas une interdiction de l'auto-rétrogradation). Sans
      // cette invalidation, useMe() ("me") continuerait de servir l'ancien
      // jeu de privilèges en cache — nav/domaines/RequirePrivilege resteraient
      // faux jusqu'à un rechargement complet.
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useEraseUser() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => client.eraseUser(userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useRequestTenantPurge() {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (vars: { tenantId: string; confirmSlug: string }) =>
      client.requestTenantPurge(vars.tenantId, vars.confirmSlug),
  });
}

export function usePurgeStatus(purgeId: string | null) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["purge-status", purgeId],
    queryFn: () => client.getPurgeStatus(purgeId as string),
    enabled: purgeId !== null,
    // Le statut ne change jamais spontanément côté client — seul un
    // nouveau GET peut le faire avancer de "en cours" à "terminé" : un
    // sondage court est le seul moyen de le savoir (même patron que
    // NotificationBell, cf. CLAUDE.md SP-39).
    refetchInterval: (query) => (query.state.data ? false : 3000),
  });
}
