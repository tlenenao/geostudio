import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { download } from "./helpers";
import { getSeed, type Seed } from "./seed";

let seed: Seed;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

function xlsxSheetXml(buf: Buffer): string {
  const dir = mkdtempSync(join(tmpdir(), "aud-j05-"));
  const file = join(dir, "x.xlsx");
  writeFileSync(file, buf);
  return execFileSync("unzip", ["-p", file, "xl/worksheets/sheet1.xml"]).toString();
}

test.describe("j05 exports — API", () => {
  test("export d'entités : CSV, XLSX, GeoJSON et GPKG servent 60 entités avec le bon type MIME", async () => {
    const base = `/v1/collections/${seed.eventsCollection}/export/items`;
    const csv = await download("analyst", "GET", `${base}?format=csv`);
    expect(csv.status).toBe(200);
    expect(csv.type).toContain("text/csv");
    expect(csv.disposition).toMatch(/attachment; filename="[^"]+\.csv"/);
    expect(csv.buf.toString().split(/\r?\n/)[0]).toBe("nom,cat,zone,date,note,montant");
    const gj = await download("analyst", "GET", `${base}?format=geojson`);
    expect(gj.type).toContain("application/geo+json");
    const fc = JSON.parse(gj.buf.toString());
    expect(fc.features).toHaveLength(60);
    expect(fc.features[1].geometry.type).toBe("Point");
    const xlsx = await download("analyst", "GET", `${base}?format=xlsx`);
    expect(xlsx.type).toContain("spreadsheetml");
    expect(xlsx.buf.subarray(0, 2).toString()).toBe("PK");
    const gpkg = await download("analyst", "GET", `${base}?format=gpkg`);
    expect(gpkg.type).toContain("geopackage");
    expect(gpkg.buf.subarray(0, 15).toString()).toBe("SQLite format 3");
    const filtered = await download("analyst", "GET", `${base}?format=csv&cat=a`);
    expect(filtered.buf.toString().trim().split("\n")).toHaveLength(1 + 18 + 1); // + ligne à saut de ligne interne
  });

  test("export : format inconnu, filtre inconnu, bbox invalide → 400 ; anonyme → 401 ; agrégat CSV/XLSX", async () => {
    const base = `/v1/collections/${seed.eventsCollection}/export/items`;
    for (const q of ["format=pdf", "format=csv&nope=1", "format=csv&bbox=abc"]) {
      expect((await download("analyst", "GET", `${base}?${q}`)).status, q).toBe(400);
    }
    expect((await download(null, "GET", `${base}?format=csv`)).status).toBe(401);
    const agg = await download(
      "analyst",
      "POST",
      `/v1/collections/${seed.ventes}/export?format=csv`,
      {
        groupBy: "zone",
        agg: "count",
      },
    );
    expect(agg.status).toBe(200);
    expect(agg.buf.toString().split(/\r?\n/)[0]).toBe("zone,value");
    const badFmt = await download(
      "analyst",
      "POST",
      `/v1/collections/${seed.ventes}/export?format=geojson`,
      {
        agg: "count",
      },
    );
    expect(badFmt.status).toBe(400);
  });

  // Finding j05-009 : cellules « =… » / « @… » écrites telles quelles (CSV) ou comme formule (XLSX).
  test.fixme("j05-009 : un texte commençant par « = » ou « @ » n'est jamais exporté comme formule", async () => {
    const path = `/v1/collections/${seed.eventsCollection}/export/items`;
    const csv = await download("analyst", "GET", `${path}?format=csv`);
    expect(csv.buf.toString()).not.toMatch(/(^|,)"?=1\+1/m);
    expect(csv.buf.toString()).not.toMatch(/(^|,)@SUM/m);
    const xlsx = await download("analyst", "GET", `${path}?format=xlsx`);
    expect(xlsxSheetXml(xlsx.buf)).not.toContain("<f>");
  });

  // Finding j05-010 : 0 octet sans en-tête quand l'agrégat ne retourne aucune ligne.
  test.fixme("j05-010 : l'export d'un agrégat vide contient au moins la ligne d'en-tête", async () => {
    const r = await download(
      "analyst",
      "POST",
      `/v1/collections/${seed.ventes}/export?format=csv`,
      {
        groupBy: "cat",
        agg: "count",
        filters: { cat: "zz" },
      },
    );
    expect(r.status).toBe(200);
    expect(r.buf.length).toBeGreaterThan(0);
  });
});
