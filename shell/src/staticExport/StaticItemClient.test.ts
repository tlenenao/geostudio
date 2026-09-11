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

  it("les révisions ne sont pas disponibles hors ligne", async () => {
    const client = createStaticItemClient(config());
    await expect(client.listConfigRevisions("app-1")).rejects.toThrow(/export statique/);
    await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow(/export statique/);
  });

  it("sampleCollectionField throws an explicit unsupported error", async () => {
    const client = createStaticItemClient(config());
    await expect(client.sampleCollectionField("c", "f", 10)).rejects.toThrow(/statique/i);
  });

  it("the four map-icon methods all throw an explicit unsupported error", async () => {
    const client = createStaticItemClient(config());
    await expect(
      client.uploadMapIcon(new File(["x"], "logo.png", { type: "image/png" }), "Logo", "generic"),
    ).rejects.toThrow(/statique/i);
    await expect(client.listMapIcons()).rejects.toThrow(/statique/i);
    await expect(client.deleteMapIcon("i1")).rejects.toThrow(/statique/i);
    await expect(client.fetchMapIconBlob("i1")).rejects.toThrow(/statique/i);
  });

  // Le reste de l'interface (SP-43 : "chaque méthode rejette explicitement
  // plutôt que d'être omise, afin que TypeScript prouve qu'aucune n'a été
  // oubliée") n'a, par construction, qu'un seul corps possible : `return
  // unsupported();`. Plutôt que dupliquer un test par méthode, on parcourt
  // toutes les clés de l'objet retourné et on vérifie génériquement que
  // chacune — hors les méthodes à comportement réel couvertes ci-dessus —
  // rejette avec le même message explicite. Un test générique unique évite
  // à la fois la duplication et le risque qu'une future méthode ajoutée à
  // ItemClient reste, elle, non couverte.
  const REAL_BEHAVIOR_METHODS = new Set([
    "getAppConfig",
    "getPublicAppConfig",
    "queryDataSource",
    "invalidateDatasetCache",
    "featuresUrl",
    "createFeature",
    "attachmentFileUrl",
    "listMapIcons",
    "deleteMapIcon",
    "fetchMapIconBlob",
    "uploadMapIcon",
    "listConfigRevisions",
    "rollbackConfig",
    "sampleCollectionField",
  ]);

  it("every other ItemClient method rejects with the same explicit unsupported error", async () => {
    const client = createStaticItemClient(config());
    const remaining = Object.entries(client).filter(([name]) => !REAL_BEHAVIOR_METHODS.has(name));
    expect(remaining.length).toBeGreaterThan(50);
    for (const [name, method] of remaining) {
      expect(typeof method, `${name} should be a function`).toBe("function");
      await expect(
        (method as (...args: unknown[]) => Promise<unknown>)(),
        `${name} should reject as unsupported`,
      ).rejects.toThrow(/statique/i);
    }
  });
});
