// SPDX-License-Identifier: Apache-2.0
import type {
  AppExportJobStatus,
  AppExportMode,
  ExportFormat,
  ExportJob,
  FieldError,
  ItemClient,
} from "../types";
import type { ItemClientBase } from "../base";
import { SqlQueryError } from "../base";

async function requestAnalyticsSql(
  coreUrl: string,
  token: string | undefined,
  sql: string,
): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${coreUrl}/analytics/sql`, {
    method: "POST",
    headers,
    body: JSON.stringify({ sql }),
  });
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as {
      errors?: FieldError[];
    } | null;
    throw new SqlQueryError(data?.errors?.[0]?.message ?? "Requête SQL invalide.");
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} POST /analytics/sql`);
  }
  return (await res.json()) as { columns: string[]; rows: unknown[][]; truncated: boolean };
}

type ExportsIngestionMethods = Pick<
  ItemClient,
  | "createExport"
  | "getExportJob"
  | "createAppExport"
  | "getAppExportJob"
  | "presignUpload"
  | "uploadToPresignedUrl"
  | "inspectUpload"
  | "createIngestionJob"
  | "getIngestionJob"
  | "runAnalyticsSql"
>;

export function createExportsIngestionMethods(base: ItemClientBase): ExportsIngestionMethods {
  const { request, coreUrl, getToken } = base;
  return {
    async createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }> {
      return request<{ jobId: string }>("POST", `/export`, { itemId, format });
    },

    async getExportJob(jobId: string): Promise<ExportJob> {
      return request<ExportJob>("GET", `/export/jobs/${jobId}`);
    },

    async createAppExport(itemId: string, mode: AppExportMode): Promise<{ jobId: string }> {
      const data = await request<{ jobId: string }>("POST", "/app-exports", { itemId, mode });
      return data;
    },

    async getAppExportJob(_itemId: string, jobId: string): Promise<AppExportJobStatus> {
      return request<AppExportJobStatus>("GET", `/app-exports/jobs/${jobId}`);
    },

    async presignUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>("POST", "/uploads/presign", {
        filename,
        contentType,
      });
    },

    async uploadToPresignedUrl(url: string, file: File) {
      const res = await fetch(url, { method: "PUT", body: file });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    },

    async inspectUpload(input: { key: string; filename: string }) {
      return request<{
        layers: { name: string; featureCount: number; geometryType: string }[];
        fields?: string[] | null;
      }>("POST", "/uploads/inspect", input);
    },

    async createIngestionJob(input) {
      return request<{ jobId: string }>("POST", "/uploads", input);
    },

    async getIngestionJob(jobId: string) {
      return request<{
        status: "pending" | "running" | "done" | "error";
        errorMessage: string | null;
        collectionId: string | null;
        itemId: string | null;
      }>("GET", `/uploads/${jobId}`);
    },

    async runAnalyticsSql(sql: string) {
      return requestAnalyticsSql(coreUrl, getToken(), sql);
    },
  };
}
