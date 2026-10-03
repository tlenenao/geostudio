// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, test, vi } from "vitest";
import {
  fetchFeatureCollection,
  hostedToken,
  listFields,
  makeSampleFieldFn,
  makeStatQueryFn,
} from "./geojsonIntrospect";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fcWithValues(field: string, values: unknown[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: values.map((v) => ({
      type: "Feature",
      properties: { [field]: v },
      geometry: null as any,
    })),
  };
}

describe("fetchFeatureCollection", () => {
  test("resolves a valid FeatureCollection", async () => {
    const fc = { type: "FeatureCollection", features: [] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).resolves.toEqual(fc);
  });

  test("attache le jeton quand il est fourni (collection privée, P29.02)", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ type: "FeatureCollection", features: [] }),
    });
    vi.stubGlobal("fetch", f);
    await fetchFeatureCollection("https://core.test/collections/c/items", "tok");
    expect(f).toHaveBeenCalledWith("https://core.test/collections/c/items", {
      headers: { Authorization: "Bearer tok" },
    });
  });

  test("hostedToken : jeton seulement pour une URL servie par le cœur", () => {
    const client = { getCoreUrl: () => "https://core.test", getAuthToken: () => "tok" };
    expect(hostedToken(client, "https://core.test/collections/c/items")).toBe("tok");
    expect(hostedToken(client, "https://evil.example/collections/c/items")).toBeUndefined();
    for (const u of [
      "https://core.test.evil.com/collections/c/items",
      "https://core.test@evil.com/collections/c/items",
      "https://evil.com/?https://core.test/collections/c/items",
      "http://core.test/collections/c/items",
      "https://core.test:8443/collections/c/items",
      "//evil.com/collections/c/items",
    ]) {
      expect(hostedToken(client, u), u).toBeUndefined();
    }
  });

  test("rejects on a non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }),
    );
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).rejects.toThrow(/404/);
  });

  test("rejects when the body is not a GeoJSON FeatureCollection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ type: "Feature" }) }),
    );
    await expect(fetchFeatureCollection("https://ex.test/d.geojson")).rejects.toThrow(
      /FeatureCollection/,
    );
  });
});

describe("listFields", () => {
  test("unions properties across heterogeneous features, sorted", () => {
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: { nom: "A", pop: 10 }, geometry: null as any },
        { type: "Feature", properties: { region: "X" }, geometry: null as any },
      ],
    };
    expect(listFields(fc)).toEqual(["nom", "pop", "region"]);
  });

  test("returns an empty list for an empty collection", () => {
    expect(listFields({ type: "FeatureCollection", features: [] })).toEqual([]);
  });
});

describe("makeStatQueryFn", () => {
  test("groupBy returns distinct values in first-appearance order", async () => {
    const fc = fcWithValues("categorie", ["a", "b", "a", "c"]);
    const rows = await makeStatQueryFn(fc)({ groupBy: "categorie" });
    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
  });

  test("measures min and max over numeric values, ignoring non-numeric ones", async () => {
    const fc = fcWithValues("pop", [30, "n/a", 10, null, 20]);
    const rows = await makeStatQueryFn(fc)({
      measures: [
        { field: "pop", agg: "min", label: "min" },
        { field: "pop", agg: "max", label: "max" },
      ],
    });
    expect(rows).toEqual([{ id: "", properties: { min: 10, max: 30 } }]);
  });

  test("measures percentile interpolates linearly over sorted values", async () => {
    const fc = fcWithValues("pop", [10, 20, 30, 40]);
    const rows = await makeStatQueryFn(fc)({
      measures: [{ field: "pop", agg: "percentile", label: "q50", p: 50 }],
    });
    expect(rows).toEqual([{ id: "", properties: { q50: 25 } }]);
  });

  test("degenerates to 0 rather than NaN on an empty collection", async () => {
    const fc = fcWithValues("pop", []);
    const rows = await makeStatQueryFn(fc)({
      measures: [
        { field: "pop", agg: "min", label: "min" },
        { field: "pop", agg: "max", label: "max" },
      ],
    });
    expect(rows).toEqual([{ id: "", properties: { min: 0, max: 0 } }]);
  });
});

describe("makeSampleFieldFn", () => {
  test("returns finite numeric values only, capped at the limit", async () => {
    const fc = fcWithValues("pop", [10, "n/a", 20, null, 30, 40]);
    const sample = await makeSampleFieldFn(fc)("pop", 2);
    // SP-42 F-shell-carte-05 : ne plus figer l'ordre en dur (slice(0, n)) —
    // seule la longueur et l'appartenance à la population sont garanties
    // maintenant que le tirage est aléatoire.
    expect(sample).toHaveLength(2);
    for (const v of sample) expect([10, 20, 30, 40]).toContain(v);
  });

  test("F-shell-carte-05 : échantillonne au hasard, pas les N premières valeurs triées du fichier", async () => {
    // Sur une FeatureCollection triée (cas réel : export par date/région/
    // ordre alphabétique), un slice(0, limit) ne verrait jamais rien
    // au-delà de `limit` — biais réel démontré par la falsification :
    // max échantillon 1999 au lieu de >4000 sur une population [0..4999].
    const n = 5000;
    const limit = 2000;
    const fc = fcWithValues(
      "value",
      Array.from({ length: n }, (_, i) => i),
    );
    const sample = await makeSampleFieldFn(fc)("value", limit);
    expect(sample).toHaveLength(limit);
    expect(Math.max(...sample)).toBeGreaterThan(4000);
  });
});
