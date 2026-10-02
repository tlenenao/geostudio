/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { apiFor, ingest, type Api } from "./api";
import { getSeed, mapConfig, type Seed } from "./seed";

// Carte issue d'un import : contenu de la config générée, versions/rollback,
// publication, droits. Niveau API (personas OIDC réelles).
test.setTimeout(120_000);

let creator: Api;
let reader: Api;
let analyst: Api;
let seed: Seed;
let big: { itemId: string; collectionId: string };

test.beforeAll(async () => {
  creator = await apiFor("creator");
  reader = await apiFor("reader");
  analyst = await apiFor("analyst");
  seed = await getSeed();
  const feats = Array.from({ length: 250 }, (_, i) => ({
    type: "Feature",
    properties: { i },
    geometry: { type: "Point", coordinates: [2 + i * 0.01, 46 + i * 0.005] },
  }));
  const res = await ingest(
    creator,
    "p250.geojson",
    Buffer.from(JSON.stringify({ type: "FeatureCollection", features: feats })),
  );
  expect(res.job.status).toBe("done");
  big = { itemId: res.job.itemId, collectionId: res.job.collectionId };
});

const put = (api: Api, pk: string, map: unknown) =>
  api.send("PUT", `/v1/configs/by-item/${pk}`, { version: 1, kind: "map", map, printLayout: null });

test.describe("j03 carte importée — contenu de la config générée", () => {
  bug(
    "j03-008 : la couche d'une carte importée charge toutes les entités (250 attendues)",
    async () => {
      // Défaut j03-008 : couche « feature » sur /collections/{id}/items sans limit → 100 entités max.
      const cfg = await mapConfig(creator, big.itemId);
      const layer = cfg.config.map.layers[0];
      if (layer.kind === "feature") {
        const r = await creator.get(new URL(layer.url).pathname + new URL(layer.url).search);
        expect(r.body.features).toHaveLength(250);
      } else {
        expect(layer.kind).toBe("vector"); // couche MVT : pas de plafond de page
      }
    },
  );

  bug(
    "j03-009 : la carte importée porte une emprise (item.bbox) exploitable par le catalogue et par « Ajuster à l'emprise »",
    async () => {
      // Défaut j03-009 : recompute_item_bbox ignore les couches sans collectionId → bbox null.
      const item = (await creator.get(`/v1/items/${seed.pointsItem}`)).body;
      expect(item.bbox).not.toBeNull();
    },
  );

  bug(
    "j03-010 : la couche de points importée déclare un rendu « points » (renderAs/geometryKind)",
    async () => {
      // Défaut j03-010 (probable) : renderAs absent → MapView retombe sur « fill », invisible pour des Point.
      const cfg = await mapConfig(creator, seed.pointsItem);
      const layer = cfg.config.map.layers[0];
      expect(layer.renderAs === "circle" || layer.kind === "vector").toBe(true);
    },
  );
});

test.describe("j03 carte — versions et rollback", () => {
  test("chaque PUT crée une version, la liste est ordonnée et le rollback restaure le contenu", async () => {
    const cfg = await mapConfig(creator, seed.pointsItem);
    const id = cfg.id;
    const v0 = cfg.version;
    const m1 = JSON.parse(JSON.stringify(cfg.config.map));
    m1.layers[0].title = "aud-j03 titre v+1";
    expect((await put(creator, seed.pointsItem, m1)).status).toBe(200);
    const m2 = JSON.parse(JSON.stringify(m1));
    m2.layers[0].title = "aud-j03 titre v+2";
    expect((await put(creator, seed.pointsItem, m2)).status).toBe(200);
    const revs = (await creator.get(`/v1/configs/${id}/revisions`)).body as any[];
    expect(revs.length).toBeGreaterThanOrEqual(v0 + 2);
    const rb = await creator.send("POST", `/v1/configs/${id}/rollback`, { version: v0 + 1 });
    expect(rb.status).toBe(200);
    const after = await mapConfig(creator, seed.pointsItem);
    expect(after.config.map.layers[0].title).toBe("aud-j03 titre v+1");
    expect(after.version).toBeGreaterThan(v0 + 2); // le rollback écrit une nouvelle version
  });

  test("rollback vers une version inexistante : 404 ; lecteur : refusé", async () => {
    const cfg = await mapConfig(creator, seed.pointsItem);
    const r = await creator.send("POST", `/v1/configs/${cfg.id}/rollback`, { version: 9999 });
    expect(r.status).toBe(404);
    const d = await reader.send("POST", `/v1/configs/${cfg.id}/rollback`, { version: 1 });
    expect([403, 404]).toContain(d.status);
  });

  test("j03-011 : la config de carte est validée côté serveur (centre, zoom, opacité, URLs)", async () => {
    // Défaut j03-011 : MapView/MapLayer sans contraintes — lat 999, zoom 99, opacité 5, url javascript:
    // sont acceptés (200) et rendront la carte inutilisable pour tout lecteur.
    const cfg = await mapConfig(creator, seed.pointsItem);
    const bad = (mut: (m: any) => void) => {
      const m = JSON.parse(JSON.stringify(cfg.config.map));
      mut(m);
      return put(creator, seed.pointsItem, m);
    };
    expect.soft((await bad((m) => (m.view.center = [2, 999]))).status).toBe(422);
    expect.soft((await bad((m) => (m.view.zoom = 99))).status).toBe(422);
    expect.soft((await bad((m) => (m.layers[0].opacity = 5))).status).toBe(422);
    expect
      .soft(
        (
          await bad((m) =>
            m.layers.push({ id: "x", title: "x", kind: "feature", url: "javascript:1" }),
          )
        ).status,
      )
      .toBe(422);
    // restaure une config saine
    await put(creator, seed.pointsItem, cfg.config.map);
  });
});

test.describe("j03 carte — publication et droits", () => {
  test("publier ouvre la config au lecteur et à l'anonyme ; dépublier la referme ; le lecteur ne peut pas écrire", async () => {
    const pk = big.itemId;
    expect((await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: true })).status).toBe(
      200,
    );
    expect((await reader.get(`/v1/configs/by-item/${pk}`)).status).toBe(200);
    const anon = await fetch(`http://localhost:8200/v1/public/configs/by-item/${pk}`);
    expect(anon.status).toBe(200);
    const w = await put(reader, pk, {
      basemap: { style: "x" },
      view: { center: [0, 0], zoom: 1 },
      layers: [],
    });
    expect(w.status).toBe(403);
    expect((await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: false })).status).toBe(
      200,
    );
    const anon2 = await fetch(`http://localhost:8200/v1/public/configs/by-item/${pk}`);
    expect(anon2.status).toBe(404);
  });

  test("l'analyste (sans maps.manage) ne peut pas modifier une carte publiée", async () => {
    const pk = big.itemId;
    await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: true });
    const cfg = await mapConfig(creator, pk);
    const r = await put(analyst, pk, cfg.config.map);
    expect([403, 404]).toContain(r.status);
    await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: false });
  });

  bug(
    "j03-012 : une carte publiée dont la collection reste privée est signalée ou publie ses données",
    async () => {
      // Défaut j03-012 : après « Publier », lecteur et anonyme reçoivent 404 sur /collections/{id}/items :
      // la carte publique est vide, sans aucun avertissement à la publication.
      const pk = big.itemId;
      await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: true });
      try {
        const r = await reader.get(`/v1/collections/${big.collectionId}/items?limit=1`);
        expect(r.status).toBe(200);
      } finally {
        await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: false });
      }
    },
  );
});
