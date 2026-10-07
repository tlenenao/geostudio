import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { apiFor, fixture, ingest, type Api } from "./api";
import { psql } from "../j02/helpers";

// Import de fichiers → collection → carte, au niveau API/worker (personas OIDC réelles).
// Les tests d'import passent par `ingest()` qui rattrape j03-001 (POST /uploads → 500
// après commit du job) et j03-002 (présigné → 500) en déposant l'objet dans le bucket
// et en déférant la tâche depuis le worker : sans ce rattrapage, aucun import n'aboutit.
test.setTimeout(120_000);

let creator: Api;
let reader: Api;
test.beforeAll(async () => {
  creator = await apiFor("creator");
  reader = await apiFor("reader");
});

test.describe("j03 import — défauts bloquants du chemin nominal", () => {
  test("j03-001 : POST /uploads répond 201 et défère le job d'ingestion", async () => {
    // Défaut j03-001 : procrastinate.exceptions.AppNotOpen → 500 après commit du job.
    const res = await ingest(
      creator,
      "points.geojson",
      fixture("points.geojson"),
      {},
      15_000,
      false,
    );
    expect(res.create.status).toBe(201);
    expect(res.job?.status).toBe("done");
  });

  test("j03-002 : POST /uploads/presign répond 200 avec une URL d'envoi", async () => {
    // Défaut j03-002 (déjà relevé par j02-002) : put_bucket_cors NotImplemented côté MinIO → 500.
    const r = await creator.send("POST", "/v1/uploads/presign", {
      filename: "a.geojson",
      contentType: "application/geo+json",
    });
    expect(r.status).toBe(200);
    expect(r.body.uploadUrl).toMatch(/^http/);
  });

  bug(
    "j03-003 : un job dont la mise en file a échoué n'est pas laissé « pending » indéfiniment",
    async () => {
      // Défaut j03-003 : POST /uploads commite le job puis échoue (j03-001) ; reclaim_stuck_jobs ne
      // balaie que « running », le job reste « pending » et le shell le sonde sans fin.
      const key = `default/zombie-${Date.now()}-a.geojson`;
      await creator.send("POST", "/v1/uploads", {
        key,
        filename: "a.geojson",
        collectionTitle: "aud-j03 zombie",
      });
      const job = psql(`SELECT id FROM ingestion_jobs WHERE source_key='${key}'`).trim();
      // Simule le passage du balayage périodique (ancienneté > seuil) : le job doit alors être en erreur.
      psql(`UPDATE ingestion_jobs SET updated_at = now() - interval '2 hours' WHERE id='${job}'`);
      await new Promise((r) => setTimeout(r, 1000));
      const st = await creator.get(`/v1/uploads/${job}`);
      expect(st.body.status).not.toBe("pending");
    },
  );
});

test.describe("j03 import — formats nominaux", () => {
  test("GeoJSON : 12 entités, SRID 4326, carte créée avec une couche « vector » (tuiles)", async () => {
    const res = await ingest(creator, "points.geojson", fixture("points.geojson"));
    expect(res.job.status).toBe("done");
    const col = (await creator.get(`/v1/collections/${res.job.collectionId}`)).body;
    expect(col.featureCount).toBe(12);
    expect(col.srid).toBe(4326);
    expect(col.geometryType).toBe("Point");
    const cfg = (await creator.get(`/v1/configs/by-item/${res.job.itemId}`)).body.config;
    expect(cfg.map.layers).toHaveLength(1);
    expect(cfg.map.layers[0].kind).toBe("vector");
    const { center, zoom } = cfg.map.view; // la vue initiale encadre les données (2..3.1, 46..46.55)
    expect(center[0]).toBeGreaterThan(2);
    expect(center[0]).toBeLessThan(3.1);
    expect(center[1]).toBeGreaterThan(46);
    expect(center[1]).toBeLessThan(46.55);
    expect(zoom).toBeGreaterThan(5);
  });

  test("GeoPackage en EPSG:2154 : reprojeté en 4326", async () => {
    const res = await ingest(creator, "l93.gpkg", fixture("l93.gpkg"));
    expect(res.job.status).toBe("done");
    const col = (await creator.get(`/v1/collections/${res.job.collectionId}`)).body;
    expect(col.srid).toBe(4326);
    const [w, s, e, n] = col.extent.spatial.bbox[0];
    // (0,0) Lambert-93 ≈ (-1.36, -5.98) en WGS84
    expect(w).toBeGreaterThan(-2);
    expect(e).toBeLessThan(0);
    expect(s).toBeGreaterThan(-7);
    expect(n).toBeLessThan(-5);
  });

  test("Shapefile zippé, GeoParquet, KML et KMZ aboutissent", async () => {
    for (const f of ["zones.zip", "geo.parquet", "z.kml", "z.kmz"]) {
      const res = await ingest(creator, f, fixture(f));
      expect(res.job?.status, f).toBe("done");
      expect(res.job.itemId, f).toBeTruthy();
    }
  });

  test("CSV lat/lon et XLSX (lat/lon explicites) aboutissent avec 2 entités", async () => {
    const csv = await ingest(creator, "latlon.csv", fixture("latlon.csv"));
    expect(csv.job.status).toBe("done");
    const xlsx = await ingest(creator, "sheet.xlsx", fixture("sheet.xlsx"), {
      latField: "lat",
      lonField: "lon",
    });
    expect(xlsx.job.status).toBe("done");
    for (const r of [csv, xlsx]) {
      const col = (await creator.get(`/v1/collections/${r.job.collectionId}`)).body;
      expect(col.featureCount).toBe(2);
    }
  });

  test("j03-021 : une collection tabulaire importée (sans géométrie) est atteignable depuis le catalogue du créateur", async () => {
    // Défaut j03-021 : run_import ne crée ni Map ni item « dataset » quand geometryMode=none (itemId null) ;
    // le Créateur n'a pas admin.collections.manage et l'import le renvoie sur « / » : la collection n'a
    // aucune entrée dans « Données » (0 item dataset) — seul le sélecteur de couches la révèle.
    const res = await ingest(creator, "nogeom.csv", fixture("nogeom.csv"), {
      geometryMode: "none",
    });
    expect(res.job.status).toBe("done");
    const mine = (await creator.get("/v1/items?type=dataset&scope=mine&pageSize=100")).body;
    expect(mine.total).toBeGreaterThan(0);
  });
});

test.describe("j03 import — erreurs", () => {
  test("GeoJSON vide, fichier de 0 octet, JSON invalide : job en erreur, message explicite, pas de collection", async () => {
    const empty = await ingest(creator, "empty.geojson", fixture("empty.geojson"));
    expect(empty.job.status).toBe("error");
    expect(empty.job.errorMessage).toMatch(/aucune entité/);
    for (const f of ["zero.geojson", "notjson.geojson"]) {
      const res = await ingest(creator, f, fixture(f));
      expect(res.job.status, f).toBe("error");
      expect(res.job.collectionId, f).toBeNull();
      expect(res.job.errorMessage, f).toMatch(/JSON invalide/);
    }
  });

  test("GeoPackage sans CRS et CSV sans colonnes lat/lon : refusés avec un message qui nomme le problème", async () => {
    const nocrs = await ingest(creator, "nocrs.gpkg", fixture("nocrs.gpkg"));
    expect(nocrs.job.status).toBe("error");
    expect(nocrs.job.errorMessage).toMatch(/CRS/);
    const csv = await ingest(creator, "nogeom.csv", fixture("nogeom.csv"));
    expect(csv.job.status).toBe("error");
    expect(csv.job.errorMessage).toMatch(/lat\/lon/);
  });

  test("j03-004 : latitude hors [-90, 90] dans un CSV est refusée", async () => {
    // Défaut j03-004 : POINT(2.1 146.1) est stocké dans geometry(Point,4326), centre de carte lat 96.15.
    const res = await ingest(creator, "badcoords.csv", fixture("badcoords.csv"), {
      latField: "latitude",
      lonField: "longitude",
    });
    expect(res.job.status).toBe("error");
  });

  test("j03-005 : un CSV « ; » avec virgule décimale est importé ou reçoit un message exploitable", async () => {
    // Défaut j03-005 : message « précisez-les » alors que le shell ne peut pas proposer de colonnes
    // (ImportFileButton découpe l'en-tête sur « , » uniquement) ; aucun moyen de terminer l'import.
    const res = await ingest(creator, "semi.csv", fixture("semi.csv"), {
      latField: "lat",
      lonField: "lon",
    });
    expect(res.job.status).toBe("done");
  });

  test("j03-006 : le message d'erreur d'un zip illisible ne fuit ni chemin temporaire ni jargon GDAL", async () => {
    // Défaut j03-006 : « '/vsizip//tmp/tmpXXXX.zip' not recognized as being in a supported file format… ».
    const res = await ingest(creator, "empty.zip", fixture("empty.zip"));
    expect(res.job.status).toBe("error");
    expect(res.job.errorMessage).not.toMatch(/\/tmp\/|\/vsizip|driver explicitly/);
  });
});

test.describe("j03 import — droits", () => {
  test("droits d'import : lecteur refusé (403), clé d'un autre tenant refusée (400), objet absent 404", async () => {
    const r = await reader.send("POST", "/v1/uploads", {
      key: "default/x-a.geojson",
      filename: "a.geojson",
      collectionTitle: "t",
    });
    expect(r.status).toBe(403);
    const foreign = await creator.send("POST", "/v1/uploads", {
      key: "othertenant/x-a.geojson",
      filename: "a.geojson",
      collectionTitle: "t",
    });
    expect(foreign.status).toBe(400);
    const i = await creator.send("POST", "/v1/uploads/inspect", {
      key: "default/inexistant-a.gpkg",
      filename: "a.gpkg",
    });
    expect(i.status).toBe(404);
  });

  test("j03-007 : le présigné d'upload est réservé à data.manage (le lecteur reçoit 403)", async () => {
    // Défaut j03-007 (code-read) : presign_upload n'appelle aucun require_privilege ; un lecteur obtient
    // une URL PUT vers le bucket d'imports dès que j03-002 est corrigé. Aujourd'hui : 500 pour tous.
    const r = await reader.send("POST", "/v1/uploads/presign", {
      filename: "a.geojson",
      contentType: "application/geo+json",
    });
    expect(r.status).toBe(403);
  });
});

test.describe("j03 import — volumétrie", () => {
  test("60 000 points GeoJSON (~6 Mo) sont importés en moins de 90 s", async () => {
    test.setTimeout(240_000);
    const feats: string[] = [];
    for (let i = 0; i < 60_000; i++) {
      feats.push(
        JSON.stringify({
          type: "Feature",
          properties: { i, cat: `c${i % 7}` },
          geometry: {
            type: "Point",
            coordinates: [-5 + (i % 1000) * 0.01, 42 + Math.floor(i / 1000) * 0.05],
          },
        }),
      );
    }
    const buf = Buffer.from(`{"type":"FeatureCollection","features":[${feats.join(",")}]}`);
    const t0 = Date.now();
    const res = await ingest(creator, "big.geojson", buf, {}, 200_000);
    expect(res.job.status).toBe("done");
    expect(Date.now() - t0).toBeLessThan(90_000);
    const col = (await creator.get(`/v1/collections/${res.job.collectionId}`)).body;
    expect(col.featureCount).toBe(60_000);
  });
});
