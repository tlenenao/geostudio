// SPDX-License-Identifier: Apache-2.0
// L8 : kit de collecte privé (GET /collections/{id}/collect-kit), revalidé par ETag.
import { parseErrorResponse, type ItemClientBase } from "../base";
import type { CollectKit, ItemClient } from "../types";

type CollectKitMethods = Pick<ItemClient, "getCollectKit">;

export function createCollectKitMethods(base: ItemClientBase): CollectKitMethods {
  const { coreUrl, authFetch } = base;
  return {
    async getCollectKit(collectionId: string, etag?: string): Promise<CollectKit | null> {
      const res = await authFetch(
        `${coreUrl}/collections/${encodeURIComponent(collectionId)}/collect-kit`,
        etag ? { headers: { "If-None-Match": `"${etag}"` } } : {},
      );
      if (res.status === 304) return null;
      if (!res.ok) throw await parseErrorResponse(res);
      return (await res.json()) as CollectKit;
    },
  };
}
