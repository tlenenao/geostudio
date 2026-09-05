// SPDX-License-Identifier: Apache-2.0
import type { ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type Tiles3dMethods = Pick<
  ItemClient,
  | "createTileset3DUpload"
  | "presignTileset3DUploadPart"
  | "completeTileset3DUpload"
  | "getTileset3DUploadJob"
  | "listHostedTerrain3DSources"
  | "presignTerrain3DUpload"
  | "createTerrain3DUpload"
  | "getTerrain3DUploadJob"
>;

export function createTiles3dMethods(base: ItemClientBase): Tiles3dMethods {
  const { request, fetchHostedTerrain3dSources } = base;
  return {
    async createTileset3DUpload(input: { filename: string; title: string }) {
      return request<{ jobId: string }>("POST", "/tileset3d/uploads", input);
    },

    async presignTileset3DUploadPart(jobId: string, partNumber: number) {
      return request<{ uploadUrl: string }>(
        "POST",
        `/tileset3d/uploads/${jobId}/parts/${partNumber}/presign`,
      );
    },

    async completeTileset3DUpload(jobId: string, parts: { partNumber: number; etag: string }[]) {
      await request<void>("POST", `/tileset3d/uploads/${jobId}/complete`, { parts });
    },

    async getTileset3DUploadJob(jobId: string) {
      return request<{
        status: "pending" | "finalizing" | "done" | "error";
        errorMessage: string | null;
        itemId: string | null;
      }>("GET", `/tileset3d/uploads/${jobId}`);
    },

    async listHostedTerrain3DSources(q?: string) {
      return fetchHostedTerrain3dSources(q);
    },

    async presignTerrain3DUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>("POST", "/terrain3d/uploads/presign", {
        filename,
        contentType,
      });
    },

    async createTerrain3DUpload(input: { key: string; filename: string; title: string }) {
      return request<{ jobId: string }>("POST", "/terrain3d/uploads", input);
    },

    async getTerrain3DUploadJob(jobId: string) {
      return request<{
        status: "uploaded" | "converting" | "done" | "error";
        errorMessage: string | null;
        itemId: string | null;
      }>("GET", `/terrain3d/uploads/${jobId}`);
    },
  };
}
