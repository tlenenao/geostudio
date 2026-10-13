// SPDX-License-Identifier: Apache-2.0
import type {
  CollectionAdmin,
  CollectionRelation,
  FeatureVersion,
  GeoJSONFeatureInput,
  ItemClient,
  RelatedRecords,
  MyEntry,
  Submission,
  SubmissionTokenInfo,
  XlsFormImportResult,
} from "../types";
import type { ItemClientBase } from "../base";
import { ApiError } from "../ApiError";
import { FeatureValidationError, parseErrorResponse } from "../base";

async function requestFeatureWrite<T>(
  authFetch: ItemClientBase["authFetch"],
  url: string,
  method: string,
  body?: GeoJSONFeatureInput,
  ifMatch?: string,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (ifMatch) headers["If-Match"] = ifMatch;
  const res = await authFetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await parseErrorResponse(res);
    // 400 (écriture de feature) ou 422 : erreurs par champ `{field, code, message}`.
    if ((res.status === 400 || res.status === 422) && err.errors) {
      throw new FeatureValidationError(err.errors);
    }
    if (res.status === 400) throw new FeatureValidationError([]);
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

type FeaturesMethods = Pick<
  ItemClient,
  | "getCollection"
  | "getCollectionPermission"
  | "createFeature"
  | "updateFeature"
  | "deleteFeature"
  | "getFeature"
  | "listFeatureHistory"
  | "restoreFeatureVersion"
  | "listCollectionRelations"
  | "listRelatedRecords"
  | "listSubmissions"
  | "approveSubmission"
  | "rejectSubmission"
  | "listSubmissionTokens"
  | "createSubmissionToken"
  | "revokeSubmissionToken"
  | "listMyEntries"
  | "importXlsForm"
>;

export function createFeaturesMethods(base: ItemClientBase): FeaturesMethods {
  const { request, coreUrl, authFetch } = base;
  return {
    async getCollection(collectionId: string): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("GET", `/collections/${collectionId}`);
    },

    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ permissions?: { write?: boolean } }>(
        "GET",
        `/collections/${collectionId}`,
      );
      return data.permissions?.write ?? false;
    },

    async createFeature(
      collectionId: string,
      feature: GeoJSONFeatureInput,
    ): Promise<{ id: string | number }> {
      return requestFeatureWrite<{ id: string | number }>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items`,
        "POST",
        feature,
      );
    },

    async updateFeature(
      collectionId: string,
      fid: string,
      feature: GeoJSONFeatureInput,
      opts?: { ifMatch?: string },
    ): Promise<void> {
      await requestFeatureWrite<void>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "PUT",
        feature,
        opts?.ifMatch,
      );
    },

    async deleteFeature(
      collectionId: string,
      fid: string,
      opts?: { ifMatch?: string },
    ): Promise<void> {
      await requestFeatureWrite<void>(
        authFetch,
        `${coreUrl}/collections/${collectionId}/items/${fid}`,
        "DELETE",
        undefined,
        opts?.ifMatch,
      );
    },

    async listFeatureHistory(collectionId: string, fid: string) {
      const data = await request<{ versions: FeatureVersion[] }>(
        "GET",
        `/collections/${collectionId}/items/${fid}/history`,
      );
      return data.versions;
    },

    async restoreFeatureVersion(collectionId: string, fid: string, versionId: number) {
      await request<void>(
        "POST",
        `/collections/${collectionId}/items/${fid}/history/${versionId}/restore`,
      );
    },

    async listCollectionRelations(collectionId: string) {
      return request<CollectionRelation[]>("GET", `/collections/${collectionId}/relations`);
    },

    async listRelatedRecords(collectionId: string, fid: string, relationId: string) {
      return request<RelatedRecords>(
        "GET",
        `/collections/${collectionId}/items/${fid}/related/${relationId}`,
      );
    },

    async listMyEntries(collectionId: string, limit = 20) {
      const data = await request<{ entries: MyEntry[] }>(
        "GET",
        `/collections/${collectionId}/my-entries?limit=${limit}`,
      );
      return data.entries;
    },

    async importXlsForm(file: File) {
      // Multipart : `request()` sérialise en JSON ; pas de Content-Type posé à la main.
      const form = new FormData();
      form.append("file", file);
      const res = await authFetch(`${coreUrl}/xlsform/import`, { method: "POST", body: form });
      if (!res.ok) {
        const e = await parseErrorResponse(res);
        throw new ApiError(e.status, { title: e.title, detail: e.detail, errors: e.errors });
      }
      return (await res.json()) as XlsFormImportResult;
    },

    async listSubmissions(collectionId: string) {
      const data = await request<{ submissions: Submission[] }>(
        "GET",
        `/collections/${collectionId}/submissions`,
      );
      return data.submissions;
    },

    async approveSubmission(collectionId: string, submissionId: string) {
      await request<unknown>(
        "POST",
        `/collections/${collectionId}/submissions/${submissionId}/approve`,
      );
    },

    async rejectSubmission(collectionId: string, submissionId: string, reason: string) {
      await request<void>(
        "POST",
        `/collections/${collectionId}/submissions/${submissionId}/reject`,
        { reason },
      );
    },

    async listSubmissionTokens(collectionId: string) {
      const data = await request<{ tokens: SubmissionTokenInfo[] }>(
        "GET",
        `/collections/${collectionId}/submission-tokens`,
      );
      return data.tokens;
    },

    async createSubmissionToken(collectionId: string, input) {
      return request<SubmissionTokenInfo & { token: string }>(
        "POST",
        `/collections/${collectionId}/submission-tokens`,
        input,
      );
    },

    async revokeSubmissionToken(collectionId: string, tokenId: string) {
      await request<void>("DELETE", `/collections/${collectionId}/submission-tokens/${tokenId}`);
    },

    async getFeature(collectionId: string, fid: string) {
      const res = await authFetch(`${coreUrl}/collections/${collectionId}/items/${fid}`);
      if (!res.ok) throw await parseErrorResponse(res);
      const f = (await res.json()) as {
        id: string | number;
        properties: Record<string, unknown>;
        geometry: unknown;
      };
      return { ...f, etag: res.headers.get("ETag") };
    },
  };
}
