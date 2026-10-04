// SPDX-License-Identifier: Apache-2.0
import type { GeocodeResult, ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type GeocodingMethods = Pick<ItemClient, "geocode">;

export function createGeocodingMethods(base: Pick<ItemClientBase, "request">): GeocodingMethods {
  return {
    async geocode(q: string, limit = 5): Promise<GeocodeResult[]> {
      const query = new URLSearchParams({ q, limit: String(limit) });
      const body = await base.request<{ results: GeocodeResult[] }>(
        "GET",
        `/geocode?${query.toString()}`,
      );
      return body.results;
    },
  };
}
