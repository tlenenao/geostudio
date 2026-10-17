// SPDX-License-Identifier: Apache-2.0
// ARC-33 : rasters COG hébergés — mêmes routes que le cœur (`/raster/*`), jumelles de tiles3d.ts.
import type { ItemClient, RasterInfo } from "../types";
import type { ItemClientBase } from "../base";

type RasterMethods = Pick<
  ItemClient,
  | "listHostedRasterSources"
  | "presignRasterUpload"
  | "createRasterUpload"
  | "getRasterUploadJob"
  | "getRasterInfo"
  | "rasterZonalStats"
>;

export function createRasterMethods(base: ItemClientBase): RasterMethods {
  const { request } = base;
  return {
    async listHostedRasterSources(q?: string) {
      const query = new URLSearchParams({ type: "raster", pageSize: "200" });
      if (q) query.set("q", q);
      const data = await request<{ items?: { pk: string; title: string }[] }>(
        "GET",
        `/items?${query.toString()}`,
      );
      return (data.items ?? []).map((item) => ({ id: item.pk, title: item.title }));
    },

    async presignRasterUpload(filename: string, contentType: string, size: number) {
      return request<{ uploadUrl: string; key: string }>("POST", "/raster/uploads/presign", {
        filename,
        contentType,
        size,
      });
    },

    async createRasterUpload(input: { key: string; filename: string; title: string }) {
      return request<{ jobId: string }>("POST", "/raster/uploads", input);
    },

    async getRasterUploadJob(jobId: string) {
      return request<{
        status: "uploaded" | "converting" | "done" | "error";
        errorMessage: string | null;
        itemId: string | null;
      }>("GET", `/raster/uploads/${jobId}`);
    },

    async getRasterInfo(itemId: string) {
      return request<RasterInfo>("GET", `/raster/${itemId}`);
    },

    async rasterZonalStats(itemId, body) {
      return request("POST", `/raster/${itemId}/zonal-stats`, body);
    },
  };
}
