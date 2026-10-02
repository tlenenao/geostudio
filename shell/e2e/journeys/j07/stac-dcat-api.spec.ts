/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, getPublicSeed, psql, type Api, type PublicSeed } from "./helpers";

// API STAC native et export DCAT-AP : nominal, pagination, erreurs, dégradation sur collection cassée.
test.setTimeout(120_000);
const tag = stamp("j07");
let seed: PublicSeed;
let admin: Api;
let creator: Api;

async function anon(path: string, init?: RequestInit): Promise<{ status: number; body: any }> {
  const r = await fetch(`${CORE_URL}${path}`, init);
  const text = await r.text();
  try {
    return { status: r.status, body: JSON.parse(text) };
  } catch {
    return { status: r.status, body: text };
  }
}

test.beforeAll(async () => {
  seed = await getPublicSeed();
  admin = await apiFor("admin");
  creator = await apiFor("creator");
});

test.describe("j07 STAC — nominal et pagination", () => {
  test("landing, conformance : catalogue racine anonyme avec liens vers les collections publiques", async () => {
    const root = await anon("/v1/stac");
    expect(root.status).toBe(200);
    expect(root.body).toMatchObject({ type: "Catalog", stac_version: "1.0.0" });
    const rels = root.body.links.filter((l: any) => l.rel === "child").map((l: any) => l.href);
    expect(rels.some((h: string) => h.endsWith(`/stac/collections/${seed.collectionId}`))).toBe(
      true,
    );
    const conf = await anon("/v1/stac/conformance");
    expect(conf.body.conformsTo).toContain("https://api.stacspec.org/v1.0.0/core");
  });

  test("collection : licence SPDX, fournisseur, emprise spatiale et temporelle déclarées", async () => {
    const c = await anon(`/v1/stac/collections/${seed.collectionId}`);
    expect(c.status).toBe(200);
    expect(c.body.license).toBe("CC-BY-4.0");
    expect(c.body.providers).toEqual([{ name: "Producteur j07", roles: ["producer"] }]);
    expect(c.body.extent.spatial.bbox[0]).toEqual([2, 46, 3.1, 46.55]);
    expect(c.body.extent.temporal.interval[0]).toEqual([
      "2020-01-01T00:00:00Z",
      "2020-12-31T23:59:59Z",
    ]);
  });

  test("pagination des collections : limit=1 fournit un lien next, offset hors bornes est vide", async () => {
    const p1 = await anon("/v1/stac/collections?limit=1");
    expect(p1.body.collections).toHaveLength(1);
    expect(p1.body.links.some((l: any) => l.rel === "next")).toBe(true);
    const far = await anon("/v1/stac/collections?offset=9999");
    expect(far.status).toBe(200);
    expect(far.body.collections).toHaveLength(0);
    expect((await anon("/v1/stac/collections?limit=0")).status).toBe(422);
    expect((await anon("/v1/stac/collections?offset=-1")).status).toBe(422);
  });

  test("items : pagination limit/offset, lien next, bbox, item unique et 404", async () => {
    const base = `/v1/stac/collections/${seed.collectionId}/items`;
    const p1 = await anon(`${base}?limit=5`);
    expect(p1.body.features).toHaveLength(5);
    const next = p1.body.links.find((l: any) => l.rel === "next");
    expect(next.href).toContain("offset=5");
    const p3 = await anon(`${base}?limit=5&offset=10`);
    expect(p3.body.features).toHaveLength(2);
    expect(p3.body.links.some((l: any) => l.rel === "next")).toBe(false);
    expect((await anon(`${base}?bbox=0,0,1,1`)).body.features).toHaveLength(0);
    expect((await anon(`${base}?bbox=1,2`)).status).toBe(400);
    expect((await anon(`${base}/1`)).status).toBe(200);
    expect((await anon(`${base}/99999`)).status).toBe(404);
    expect((await anon(`/v1/stac/collections/inconnue/items`)).status).toBe(404);
  });

  test("search : pagination par jeton, filtre collections/ids, bbox invalide en 400", async () => {
    const q = `/v1/stac/search?collections=${seed.collectionId}&limit=5`;
    const p1 = await anon(q);
    expect(p1.body.features).toHaveLength(5);
    const nextHref = p1.body.links.find((l: any) => l.rel === "next").href as string;
    const p2 = await anon(nextHref.replace("http://localhost:8200", ""));
    expect(p2.body.features).toHaveLength(5);
    expect(p2.body.features[0].id).not.toBe(p1.body.features[0].id);
    const ids = await anon(`/v1/stac/search?collections=${seed.collectionId}&ids=1,2`);
    expect(ids.body.features.map((f: any) => f.id).sort()).toEqual(["1", "2"]);
    expect((await anon("/v1/stac/search?bbox=1,2")).status).toBe(400);
    expect((await anon("/v1/stac/search?limit=0")).status).toBe(422);
    const post = await anon("/v1/stac/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ collections: [seed.collectionId], limit: 3 }),
    });
    expect(post.body.features).toHaveLength(3);
  });

  test("une collection privée n'apparaît ni dans le catalogue ni dans la recherche anonymes", async () => {
    const title = `${tag}-privee`;
    const made = await creator.send("POST", "/v1/collections/empty", {
      title,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    expect(made.status).toBe(201);
    const id = made.body.id as string;
    expect((await anon(`/v1/stac/collections/${id}`)).status).toBe(404);
    const list = await anon("/v1/stac/collections?limit=1000");
    expect(list.body.collections.map((c: any) => c.id)).not.toContain(id);
    const dcat = await anon("/v1/dcat/catalog?limit=1000");
    expect(JSON.stringify(dcat.body)).not.toContain(id);
  });
});

test.describe("j07 DCAT-AP — export", () => {
  test("dataset : licence, contact, périodicité, provenance, version et temporel mappés", async () => {
    const r = await fetch(`${CORE_URL}/v1/dcat/datasets/${seed.collectionId}`);
    expect(r.headers.get("content-type")).toContain("application/ld+json");
    const d: any = await r.json();
    expect(d["dct:license"]["@id"]).toContain("licence/CC_BY");
    expect(d["dcat:contactPoint"]["vcard:hasEmail"]).toBe("mailto:steward@example.org");
    expect(d["dct:accrualPeriodicity"]["@id"]).toContain("frequency/DAILY");
    expect(d["dct:provenance"]["rdfs:label"]).toBe("Import de test j07");
    expect(d["dct:hasVersion"]).toBe("1.0");
    expect(d["dct:language"]["@id"]).toContain("language/FRA");
    expect(d["dct:temporal"]["dcat:startDate"]["@value"]).toBe("2020-01-01");
    expect(d["dct:temporal"]["dcat:endDate"]["@value"]).toBe("2020-12-31");
    expect(d["dct:accessRights"]["@id"]).toContain("access-right/PUBLIC");
    expect(d["dcat:distribution"].length).toBeGreaterThanOrEqual(2);
  });

  test("catalogue : pagination, offset hors bornes, limit=0 en 422, dataset inconnu en 404", async () => {
    const p1 = await anon("/v1/dcat/catalog?limit=1");
    expect(p1.body["@type"]).toBe("dcat:Catalog");
    expect(p1.body["dcat:dataset"]).toHaveLength(1);
    expect(p1.body.links[0].rel).toBe("next");
    const far = await anon("/v1/dcat/catalog?offset=9999");
    expect(far.status).toBe(200);
    expect(far.body["dcat:dataset"]).toHaveLength(0);
    expect((await anon("/v1/dcat/catalog?limit=0")).status).toBe(422);
    expect((await anon("/v1/dcat/datasets/inconnu")).status).toBe(404);
  });

  test("les champs sensibles n'apparaissent dans aucune distribution ni propriété DCAT", async () => {
    const d = await anon(`/v1/dcat/datasets/${seed.collectionId}`);
    expect(JSON.stringify(d.body)).not.toMatch(/"pop"/);
  });
});

test.describe("j07 collection cassée — dégradation gracieuse", () => {
  async function withBrokenCollection(run: (id: string) => Promise<void>): Promise<void> {
    const made = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-cassee`,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    const id = made.body.id as string;
    await creator.send("PATCH", `/v1/collections/${id}`, { isPublic: true });
    psql(`DROP TABLE ${made.body.tableName} CASCADE`);
    try {
      await run(id);
    } finally {
      await admin.send("DELETE", `/v1/collections/${id}`);
    }
  }

  test("DCAT (catalogue et dataset) et STAC /collections dégradent en 200 sur une table supprimée", async () => {
    await withBrokenCollection(async (id) => {
      expect((await anon(`/v1/dcat/datasets/${id}`)).status).toBe(200);
      expect((await anon("/v1/dcat/catalog?limit=1000")).status).toBe(200);
      expect((await anon("/v1/stac/collections?limit=1000")).status).toBe(200);
      const meta = await creator.get(`/v1/collections/${id}`);
      expect(meta.status).toBe(200);
      expect((await creator.get(`/v1/collections/${id}/schema`)).status).toBe(404);
    });
  });

  // Findings j07-008 et j07-009.
  test("j07-008 : une collection cassée ne fait pas échouer /stac/search pour toutes les autres", async () => {
    await withBrokenCollection(async () => {
      const r = await anon("/v1/stac/search?limit=1000");
      expect(r.status).toBe(200);
    });
  });

  test("j07-009 : une collection cassée répond une erreur claire (pas 500) sur STAC et OGC items", async () => {
    await withBrokenCollection(async (id) => {
      for (const p of [
        `/v1/stac/collections/${id}`,
        `/v1/stac/collections/${id}/items`,
        `/v1/collections/${id}/items`,
      ]) {
        const r = await anon(p);
        expect(r.status, p).not.toBe(500);
      }
    });
  });
});

test.describe("j07 STAC — défauts constatés", () => {
  // Finding j07-010 : datetime invalide → 500.
  test("j07-010 : un paramètre datetime invalide répond 400", async () => {
    expect((await anon("/v1/stac/search?datetime=garbage")).status).toBe(400);
    const post = await anon("/v1/stac/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ collections: [seed.collectionId], datetime: "nope" }),
    });
    expect(post.status).toBe(400);
  });

  // Finding j07-011 : le filtre datetime ignore l'emprise temporelle déclarée et la propriété
  // datetime des items est la date de mise à jour de la collection.
  test("j07-011 : datetime cohérent avec l'emprise temporelle déclarée (2020)", async () => {
    const r = await anon(
      `/v1/stac/search?collections=${seed.collectionId}&datetime=2020-06-01T00:00:00Z/2020-06-30T00:00:00Z`,
    );
    expect(r.body.features.length).toBeGreaterThan(0);
    const item = await anon(`/v1/stac/collections/${seed.collectionId}/items/1`);
    expect(item.body.properties.datetime.startsWith("2020")).toBe(true);
  });

  // Finding j07-012 : licence « other » invalide en STAC 1.0 et licenseUri non exposée.
  test("j07-012 : une collection sans licence connue n'expose pas license=other et publie le lien de licence", async () => {
    const made = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-other`,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    const id = made.body.id as string;
    await creator.send("PATCH", `/v1/collections/${id}`, {
      isPublic: true,
      license: "other",
      licenseUri: "https://example.org/ma-licence",
    });
    const c = await anon(`/v1/stac/collections/${id}`);
    expect(["proprietary", "various"]).toContain(c.body.license);
    expect(c.body.links.some((l: any) => l.rel === "license")).toBe(true);
  });

  // Finding j07-013 : jeton de pagination invalide ignoré silencieusement.
  test("j07-013 : un jeton de pagination invalide est refusé (400)", async () => {
    const r = await anon(`/v1/stac/search?collections=${seed.collectionId}&token=@@@`);
    expect(r.status).toBe(400);
  });
});
