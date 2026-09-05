// SPDX-License-Identifier: Apache-2.0
import type {
  AdminExtension,
  AdminToolName,
  ExtensionManifest,
  HarvestSource,
  HarvestSourceCreateInput,
  HarvestSourcePatchInput,
  ItemClient,
} from "../types";
import type { ItemClientBase } from "../base";

type ExtensionsAdminToolsMethods = Pick<
  ItemClient,
  | "listActiveExtensions"
  | "listAllExtensions"
  | "setExtensionEnabled"
  | "launchAdminTool"
  | "listHarvestSources"
  | "createHarvestSource"
  | "updateHarvestSource"
  | "deleteHarvestSource"
  | "runHarvestSource"
>;

export function createExtensionsAdminToolsMethods(
  base: ItemClientBase,
): ExtensionsAdminToolsMethods {
  const { request, coreUrl, getToken } = base;
  return {
    async listActiveExtensions(): Promise<ExtensionManifest[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string;
          tag: string;
          label: string;
          moduleUrl: string;
          props: ExtensionManifest["props"];
          events?: string[];
          actions?: string[];
          defaultSize: { w: number; h: number };
          permissions?: { collections: string[] | "all" };
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id,
        tag: e.tag,
        label: e.label,
        moduleUrl: e.moduleUrl,
        props: e.props,
        events: e.events,
        actions: e.actions,
        defaultSize: e.defaultSize,
        permissions: e.permissions,
      }));
    },

    async listAllExtensions(): Promise<AdminExtension[]> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/extensions?all=true`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /extensions`);
      const data = (await res.json()) as {
        extensions?: Array<{
          id: string;
          tag: string;
          label: string;
          moduleUrl: string;
          props: ExtensionManifest["props"];
          events?: string[];
          actions?: string[];
          defaultSize: { w: number; h: number };
          permissions?: { collections: string[] | "all" };
          enabled: boolean;
        }>;
      };
      return (data.extensions ?? []).map((e) => ({
        type: e.id,
        tag: e.tag,
        label: e.label,
        moduleUrl: e.moduleUrl,
        props: e.props,
        events: e.events,
        actions: e.actions,
        defaultSize: e.defaultSize,
        permissions: e.permissions,
        enabled: e.enabled,
      }));
    },

    async setExtensionEnabled(id: string, enabled: boolean): Promise<void> {
      await request<void>("PATCH", `/extensions/${id}`, { enabled });
    },

    async launchAdminTool(tool: AdminToolName): Promise<{ url: string }> {
      return request<{ url: string }>("POST", `/admin-tools/launch/${tool}`);
    },

    async listHarvestSources(): Promise<HarvestSource[]> {
      const data = await request<{ sources: HarvestSource[] }>("GET", `/harvest/sources`);
      return data.sources ?? [];
    },

    async createHarvestSource(input: HarvestSourceCreateInput): Promise<HarvestSource> {
      return request<HarvestSource>("POST", `/harvest/sources`, input);
    },

    async updateHarvestSource(id: string, patch: HarvestSourcePatchInput): Promise<HarvestSource> {
      return request<HarvestSource>("PATCH", `/harvest/sources/${id}`, patch);
    },

    async deleteHarvestSource(id: string): Promise<void> {
      await request<void>("DELETE", `/harvest/sources/${id}`);
    },

    async runHarvestSource(id: string): Promise<void> {
      await request<void>("POST", `/harvest/sources/${id}/run`);
    },
  };
}
