// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig } from "../api/types";

function config(): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [
      {
        id: "s1",
        type: "static",
        service: "core",
        layer: "",
        query: { records: [{ id: 1, properties: { name: "Alpha" } }] },
      },
    ],
    messages: [],
    pages: [
      { id: "p1", name: "P1", layout: { type: "grid", breakpoints: {}, items: [] }, onEnter: [] },
    ],
    navigationMode: "tabs",
    variables: [],
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

  // I6 regression: featuresUrl() has a synchronous (non-Promise) signature
  // and can be called during render (e.g. ExplorerDrawer builds a
  // MapConfig on every render). Throwing there — as this used to — blanks
  // the whole page with no recovery. It must resolve to an inert
  // placeholder instead.
  it("featuresUrl does not throw and returns an inert placeholder", () => {
    const client = createStaticItemClient(config());
    let result: string | undefined;
    expect(() => {
      result = client.featuresUrl(config().dataSources[0]);
    }).not.toThrow();
    expect(result).toBe("about:blank");
  });
});
