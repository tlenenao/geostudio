// SPDX-License-Identifier: Apache-2.0
import type {
  AdminExtension,
  AdminToolName,
  ExtensionCreateInput,
  ExtensionPatchInput,
  ExtensionManifest,
  HarvestSource,
  HarvestSourceCreateInput,
  HarvestSourcePatchInput,
  HarvestSourceRecordsPage,
  InstanceStatus,
  JobsBacklog,
  ItemClient,
} from "../types";
import type { ItemClientBase } from "../base";
import { ensureOk } from "../base";

type ExtensionsAdminToolsMethods = Pick<
  ItemClient,
  | "listActiveExtensions"
  | "listAllExtensions"
  | "setExtensionEnabled"
  | "createExtension"
  | "updateExtension"
  | "deleteExtension"
  | "launchAdminTool"
  | "getInstanceStatus"
  | "getJobsBacklog"
  | "listHarvestSources"
  | "createHarvestSource"
  | "updateHarvestSource"
  | "deleteHarvestSource"
  | "runHarvestSource"
  | "listHarvestSourceRecords"
>;

// Ligne renvoyée par GET /extensions (`_extension_json` côté cœur).
type ExtensionRow = Omit<ExtensionManifest, "type"> & { id: string };

function toManifest(e: ExtensionRow): ExtensionManifest {
  const { id, ...rest } = e;
  return { ...rest, type: id };
}

export function createExtensionsAdminToolsMethods(
  base: ItemClientBase,
): ExtensionsAdminToolsMethods {
  const { request, coreUrl, authFetch } = base;
  return {
    async listActiveExtensions(): Promise<ExtensionManifest[]> {
      const res = await authFetch(`${coreUrl}/extensions`);
      await ensureOk(res);
      const data = (await res.json()) as { extensions?: ExtensionRow[] };
      return (data.extensions ?? []).map(toManifest);
    },

    async listAllExtensions(): Promise<AdminExtension[]> {
      const res = await authFetch(`${coreUrl}/extensions?all=true`);
      await ensureOk(res);
      const data = (await res.json()) as {
        extensions?: Array<ExtensionRow & { enabled: boolean }>;
      };
      return (data.extensions ?? []).map((e) => ({ ...toManifest(e), enabled: e.enabled }));
    },

    async setExtensionEnabled(id: string, enabled: boolean): Promise<void> {
      await request<void>("PATCH", `/extensions/${id}`, { enabled });
    },

    async createExtension(input: ExtensionCreateInput): Promise<void> {
      await request<void>("POST", `/extensions`, input);
    },

    async updateExtension(id: string, patch: ExtensionPatchInput): Promise<void> {
      await request<void>("PATCH", `/extensions/${encodeURIComponent(id)}`, patch);
    },

    async deleteExtension(id: string): Promise<void> {
      await request<void>("DELETE", `/extensions/${encodeURIComponent(id)}`);
    },

    async launchAdminTool(tool: AdminToolName): Promise<{ url: string }> {
      return request<{ url: string }>("POST", `/admin-tools/launch/${tool}`);
    },

    async getJobsBacklog(): Promise<JobsBacklog | null> {
      // /health n'est pas versionné (cf. base.ts) : on retire le suffixe /v1.
      const res = await base.fetchUrl(`${coreUrl.replace(/\/v1$/, "")}/health`);
      if (!res.ok) return null;
      const data = (await res.json()) as { jobsBacklog?: JobsBacklog | null };
      return data.jobsBacklog ?? null;
    },

    async getInstanceStatus(): Promise<InstanceStatus> {
      return request<InstanceStatus>("GET", "/instance/status");
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

    async listHarvestSourceRecords(
      id: string,
      params?: { limit?: number; offset?: number },
    ): Promise<HarvestSourceRecordsPage> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const suffix = query.size > 0 ? `?${query.toString()}` : "";
      return request<HarvestSourceRecordsPage>("GET", `/harvest/sources/${id}/records${suffix}`);
    },
  };
}
