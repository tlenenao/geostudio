// SPDX-License-Identifier: Apache-2.0
import type {
  ItemClient,
  Me,
  PrivilegeCatalogEntry,
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
        tenantSlug: string;
      }>("GET", `/me`);
      return {
        username: data.username,
        firstName: data.firstName,
        lastName: data.lastName,
        role: data.role,
        privileges: data.privileges,
        version: data.version,
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
  };
}
