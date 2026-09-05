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
