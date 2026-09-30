import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { getSeed } from "./seed";

// Droits et visibilité d'un lecteur (persona audit-reader, rôle « Lecteur »,
// aucun privilège) vus depuis l'API du cœur, jeton Keycloak réel.
test.describe("j02 lecteur — API : visibilité et droits", () => {
  test("le lecteur ne voit que les items partagés avec son groupe (scope=all)", async () => {
    const s = await getSeed();
    const page = await s.reader.get("/v1/items?pageSize=200");
    const titles: string[] = page.body.items.map((i: { title: string }) => i.title);
    expect(titles).toContain(`${s.tag}-carte`);
    expect(titles).toContain(`${s.tag}-app-publique`);
    expect(titles).not.toContain(`${s.tag}-carte-privee`);
    expect(titles).not.toContain(`${s.tag}-ds-prive`);
    expect(titles).not.toContain(`${s.tag}-app-privee`);
  });

  test("items, configs, collections, tuiles et STAC privés : 404 (pas 403, pas de fuite d'existence)", async () => {
    const s = await getSeed();
    const r = s.reader;
    for (const p of [
      `/v1/items/${s.privateMap}`,
      `/v1/configs/by-item/${s.privateMap}`,
      `/v1/collections/${s.privateCol}`,
      `/v1/collections/${s.privateCol}/schema`,
      `/v1/collections/${s.privateCol}/items`,
      `/v1/collections/${s.privateCol}/tiles/8/129/90.mvt`,
      `/v1/stac/collections/${s.privateCol}`,
      `/v1/dcat/datasets/${s.privateCol}`,
    ]) {
      expect((await r.get(p)).status, p).toBe(404);
    }
    const stac = await r.get("/v1/stac/search?limit=200");
    expect(JSON.stringify(stac.body)).not.toContain(s.privateCol);
    const cols = await r.get("/v1/collections");
    expect(JSON.stringify(cols.body)).not.toContain(s.privateCol);
  });

  test("le lecteur lit ce qui lui est partagé (item, config, collection, entités, tuile)", async () => {
    const s = await getSeed();
    const r = s.reader;
    expect((await r.get(`/v1/items/${s.sharedMap}`)).body.permissions).toEqual({
      read: true,
      write: false,
      delete: false,
      share: false,
    });
    expect((await r.get(`/v1/configs/by-item/${s.sharedMap}`)).status).toBe(200);
    const feats = await r.get(`/v1/collections/${s.sharedCol}/items`);
    expect(feats.status).toBe(200);
    expect(feats.body.numberReturned).toBe(3);
    expect((await r.get(`/v1/collections/${s.sharedCol}/tiles/8/129/90.mvt`)).status).toBeLessThan(
      300,
    );
  });

  test("toutes les écritures et surfaces d'administration sont refusées (403)", async () => {
    const s = await getSeed();
    const r = s.reader;
    const mapCfg = {
      kind: "map",
      map: { basemap: { style: "x" }, view: { center: [0, 0], zoom: 1 }, layers: [] },
    };
    const denied: [string, string, unknown?][] = [
      ["PATCH", `/v1/items/${s.sharedMap}`, { title: "hack" }],
      ["DELETE", `/v1/items/${s.sharedMap}`],
      ["PUT", `/v1/items/${s.sharedMap}/sharing`, { public: true, groups: [] }],
      ["POST", `/v1/items/${s.sharedMap}/share-links`, { ttlDays: 1 }],
      ["PUT", `/v1/configs/by-item/${s.sharedMap}`, mapCfg],
      ["DELETE", `/v1/configs/by-item/${s.sharedMap}`],
      ["POST", "/v1/configs", { title: "aud-j02-reader-map", config: mapCfg }],
      [
        "POST",
        "/v1/configs",
        {
          title: "aud-j02-reader-bm",
          config: { kind: "bookmark", bookmark: { appId: s.sharedApp, pageId: "p1" } },
        },
      ],
      ["POST", "/v1/groups", { name: "aud-j02-reader-group" }],
      ["POST", "/v1/collections/empty", { title: "aud-j02-reader-col", columns: [] }],
      ["PATCH", `/v1/collections/${s.sharedCol}`, { title: "hack" }],
      ["PUT", `/v1/collections/${s.sharedCol}/sharing`, { public: true, groups: [] }],
      ["DELETE", `/v1/collections/${s.sharedCol}`],
      [
        "POST",
        `/v1/collections/${s.sharedCol}/items`,
        { type: "Feature", geometry: null, properties: {} },
      ],
      ["POST", "/v1/analytics/sql", { sql: "select 1" }],
      ["GET", "/v1/users"],
      ["GET", "/v1/roles"],
      ["GET", "/v1/secrets"],
      ["GET", "/v1/harvest/sources"],
    ];
    for (const [m, p, b] of denied) {
      const x = await r.send(m, p, b);
      expect(x.status, `${m} ${p}`).toBe(403);
    }
  });

  // j02-001 : un `scope` inconnu supprime tout le filtre de visibilité.
  bug("j02-001 : un scope inconnu ne doit pas exposer les items privés d'autrui", async () => {
    const s = await getSeed();
    for (const scope of ["bogus", "", "owned"]) {
      const page = await s.reader.get(`/v1/items?scope=${scope}&pageSize=200`);
      const titles: string[] = page.body.items.map((i: { title: string }) => i.title);
      expect(titles, `scope=${scope}`).not.toContain(`${s.tag}-carte-privee`);
    }
    const facets = await s.reader.get("/v1/items/facets?scope=bogus");
    const all = await s.reader.get("/v1/items/facets");
    expect(facets.body).toEqual(all.body);
  });

  // j02-005 : GET /groups liste tout le tenant et GET /items/{id}/sharing n'exige que `read`.
  bug(
    "j02-005 : un lecteur ne lit ni les groupes d'autrui ni l'ACL d'un item qu'il ne peut pas partager",
    async () => {
      const s = await getSeed();
      await s.creator.send("POST", "/v1/groups", { name: `${s.tag}-groupe-secret` });
      const groups = await s.reader.get("/v1/groups");
      const names: string[] = groups.body.map((g: { name: string }) => g.name);
      expect(names).not.toContain(`${s.tag}-groupe-secret`);
      const acl = await s.reader.get(`/v1/items/${s.sharedMap}/sharing`);
      expect(acl.status).toBe(403);
    },
  );
});
