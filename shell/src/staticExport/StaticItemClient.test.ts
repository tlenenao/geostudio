// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig } from "../api/types";

function config(): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [
      { id: "s1", type: "static", service: "core", layer: "", query: { records: [{ id: 1, properties: { name: "Alpha" } }] } },
    ],
    messages: [], pages: [{ id: "p1", name: "P1", layout: { type: "grid", breakpoints: {}, items: [] }, onEnter: [] }],
    navigationMode: "tabs", variables: [],
  } as unknown as AppConfig;
}

describe("StaticItemClient", () => {
  it("getAppConfig returns the embedded config", async () => {
    const client = createStaticItemClient(config());
    const result = await client.getAppConfig("any-pk");
    expect(result.kind).toBe("app");
    expect(result.pages).toHaveLength(1);
  });

  it("queryDataSource resolves static records from the embedded query", async () => {
    const client = createStaticItemClient(config());
    const records = await client.queryDataSource(config().dataSources[0]);
    expect(records).toEqual([{ id: 1, properties: { name: "Alpha" } }]);
  });

  it("createFeature throws an explicit unsupported error", async () => {
    const client = createStaticItemClient(config());
    await expect(
      client.createFeature("col1", { type: "Feature", properties: {}, geometry: null }),
    ).rejects.toThrow(/statique/i);
  });
});
