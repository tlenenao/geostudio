// SPDX-License-Identifier: Apache-2.0
import type {
  ItemClient,
  Me,
  PrivilegeCatalogEntry,
  PurgeReceipt,
  Role,
  RoleCreateInput,
  RolePatchInput,
  RoleSummary,
  UserSummary,
} from "../types";
import type { ItemClientBase } from "../base";

type IdentityMethods = Pick<
  ItemClient,
  | "getMe"
  | "getPrivilegeCatalog"
  | "listRoles"
  | "createRole"
  | "updateRole"
  | "deleteRole"
  | "listUsers"
  | "updateUserRole"
  | "eraseUser"
  | "requestTenantPurge"
  | "getPurgeStatus"
>;

export function createIdentityMethods(base: ItemClientBase): IdentityMethods {
  const { request } = base;
  return {
    async getMe(): Promise<Me> {
      const data = await request<{
        username: string;
        firstName: string;
        lastName: string;
        role: RoleSummary;
        privileges: string[];
        version: string;
        tenantId: string;
        tenantSlug: string;
      }>("GET", `/me`);
      return {
        username: data.username,
        firstName: data.firstName,
        lastName: data.lastName,
        role: data.role,
        privileges: data.privileges,
        version: data.version,
        tenantId: data.tenantId,
        tenantSlug: data.tenantSlug,
      };
    },

    async getPrivilegeCatalog(): Promise<PrivilegeCatalogEntry[]> {
      return request<PrivilegeCatalogEntry[]>("GET", "/roles/catalog");
    },

    async listRoles(): Promise<Role[]> {
      return request<Role[]>("GET", "/roles");
    },

    async createRole(input: RoleCreateInput): Promise<Role> {
      return request<Role>("POST", "/roles", input);
    },

    async updateRole(id: string, patch: RolePatchInput): Promise<Role> {
      return request<Role>("PATCH", `/roles/${id}`, patch);
    },

    async deleteRole(id: string): Promise<void> {
      await request<void>("DELETE", `/roles/${id}`);
    },

    async listUsers(params: {
      page: number;
      pageSize: number;
      q?: string;
    }): Promise<{ users: UserSummary[]; total: number }> {
      const query = new URLSearchParams({
        page: String(params.page),
        pageSize: String(params.pageSize),
      });
      if (params.q) query.set("q", params.q);
      return request<{ users: UserSummary[]; total: number }>("GET", `/users?${query.toString()}`);
    },

    async updateUserRole(id: string, roleId: string): Promise<UserSummary> {
      return request<UserSummary>("PATCH", `/users/${id}`, { roleId });
    },

    async eraseUser(userId: string): Promise<void> {
      await request<void>("POST", `/compliance/users/${userId}/erase`);
    },

    async requestTenantPurge(tenantId: string, confirmSlug: string): Promise<{ jobId: string }> {
      return request<{ jobId: string }>("POST", `/compliance/tenants/${tenantId}/purge`, {
        confirmSlug,
      });
    },

    async getPurgeStatus(purgeId: string): Promise<PurgeReceipt | null> {
      // 202 (encore en cours) et 200 (terminé) partagent le même chemin
      // "réponse ok" côté fetch (Response.ok couvre tout 2xx) — seule la
      // FORME du corps distingue les deux (cf. app/compliance/routes.py::
      // get_purge_status) : un reçu réel porte "id", le corps 202 non.
      const data = await request<Record<string, unknown>>("GET", `/compliance/purges/${purgeId}`);
      return "id" in data ? (data as unknown as PurgeReceipt) : null;
    },
  };
}
