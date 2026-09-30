import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { getBigSeed, timed, withPeakMem, type BigSeed } from "./helpers";

// Exports d'entités (GET /v1/collections/{id}/export/items) sur des volumes réalistes.
// Les jeux de données sont créés par POST /v1/collections/empty + INSERT ... generate_series
// (POST /v1/uploads répond 500, j03-001).
let s10k: BigSeed;
let s10k1: BigSeed;
let s500k: BigSeed;

const exp = (id: string, q: string) => `/v1/collections/${id}/export/items?${q}`;

test.beforeAll(async () => {
  test.setTimeout(600_000);
  s10k = await getBigSeed(10_000);
  s10k1 = await getBigSeed(10_001);
  s500k = await getBigSeed(500_000);
});

test.describe("t03b export d'entités à l'échelle", () => {
  test("10 000 entités (le plafond exact) : CSV, GeoJSON, GPKG et XLSX répondent 200 sous 10 s", async () => {
    const out: string[] = [];
    for (const format of ["csv", "geojson", "gpkg", "xlsx"]) {
      const m = await withPeakMem("geostudio-core-1", () =>
        timed("creator", exp(s10k.collectionId, `format=${format}`)),
      );
      const r = m.value;
      out.push(`${format}=${r.ms}ms/${Math.round(r.bytes / 1024)}Ko/pic${m.peakMb}Mo`);
      expect(r.status, format).toBe(200);
      expect(r.ms, format).toBeLessThan(10_000);
      if (format === "geojson") expect(JSON.parse(r.text()).features).toHaveLength(10_000);
    }
    console.log("T03B export10k", out.join(" "));
  });

  test("10 001 entités : 413 « too many entities » (plafond confirmé à l'unité près)", async () => {
    const r = await timed("creator", exp(s10k1.collectionId, "format=csv"));
    console.log("T03B export10001", r.status, r.ms, "ms", r.text().slice(0, 120));
    expect(r.status).toBe(413);
    expect(JSON.parse(r.text()).detail).toMatch(/too many entities/);
  });

  test("500 000 entités sans filtre : 413 rendu en moins de 2 s, sans gonfler la mémoire du cœur", async () => {
    const m = await withPeakMem("geostudio-core-1", () =>
      timed("creator", exp(s500k.collectionId, "format=geojson")),
    );
    console.log(
      "T03B export500k",
      m.value.status,
      m.value.ms,
      "ms core",
      m.startMb,
      "->",
      m.peakMb,
    );
    expect(m.value.status).toBe(413);
    expect(m.value.ms).toBeLessThan(2000);
    expect(m.peakMb - m.startMb).toBeLessThan(150);
  });

  bug(
    "t03b-003 : l'export CSV/XLSX d'une collection géométrique conserve la géométrie",
    async () => {
      // Constat : features_to_format() ne passe que feature['properties'] à rows_to_format().
      const r = await timed("creator", exp(s10k.collectionId, "format=csv&bbox=-5,42,-3.7,43"));
      const header = r.text().split(/\r?\n/)[0].toLowerCase();
      expect(header).toMatch(/geom|wkt|lon|lat|x,y/);
    },
  );

  test("agrégat exporté (POST /export) sur 500 000 entités : CSV en moins de 3 s, 8 catégories", async () => {
    const r = await timed("creator", `/v1/collections/${s500k.collectionId}/export?format=csv`, {
      method: "POST",
      body: { groupBy: "cat", measures: [{ agg: "count", label: "n" }] },
    });
    const lines = r.text().trim().split(/\r?\n/);
    console.log("T03B exportAgg500k", r.status, r.ms, "ms", lines.length - 1, "lignes");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(3000);
    expect(lines.length - 1).toBe(8);
  });
});
