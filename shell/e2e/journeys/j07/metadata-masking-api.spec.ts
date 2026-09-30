/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, getPublicSeed, psql, type Api, type PublicSeed } from "./helpers";

// Licences / métadonnées ouvertes par collection et masquage de champ sensible (GAP-22).
test.setTimeout(120_000);
const tag = stamp("j07");
let seed: PublicSeed;
let admin: Api;
let creator: Api;
let analyst: Api;
let reader: Api;

test.beforeAll(async () => {
  seed = await getPublicSeed();
  [admin, creator, analyst, reader] = await Promise.all([
    apiFor("admin"),
    apiFor("creator"),
    apiFor("analyst"),
    apiFor("reader"),
  ]);
});

async function anonGet(path: string): Promise<{ status: number; body: any }> {
  const r = await fetch(`${CORE_URL}${path}`);
  return { status: r.status, body: await r.json().catch(() => null) };
}

async function newCollection(title: string): Promise<{ id: string; table: string }> {
  const made = await creator.send("POST", "/v1/collections/empty", {
    title,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "secret", sqlType: "text" },
    ],
    geometryType: "Point",
    srid: 4326,
  });
  expect(made.status).toBe(201);
  return { id: made.body.id, table: made.body.tableName };
}

test.describe("j07 métadonnées ouvertes — collection", () => {
  test("le catalogue de métadonnées liste licences, fréquences et langues", async () => {
    const r = await creator.get("/v1/metadata-catalog");
    expect(r.status).toBe(200);
    expect(r.body.licenses.map((l: any) => l.id)).toEqual(
      expect.arrayContaining(["etalab-2.0", "cc-by-4.0", "odbl-1.0", "other"]),
    );
    expect(r.body.frequencies.length).toBeGreaterThan(3);
    expect(r.body.languages.map((l: any) => l.id)).toContain("fr");
    expect((await fetch(`${CORE_URL}/v1/metadata-catalog`)).status).toBe(401);
  });

  test("les 10 champs se relisent à l'identique via GET /collections/{id}", async () => {
    const r = await creator.get(`/v1/collections/${seed.collectionId}`);
    expect(r.body).toMatchObject({
      license: "cc-by-4.0",
      licenseUri: "https://example.org/licence",
      producer: "Producteur j07",
      contact: "steward@example.org",
      updateFrequency: "daily",
      lineage: "Import de test j07",
      language: "fr",
      version: "1.0",
      temporalStart: "2020-01-01",
      temporalEnd: "2020-12-31",
    });
  });

  test("identifiants inconnus (licence, fréquence, langue) refusés en 422", async () => {
    const { id } = await newCollection(`${tag}-meta-invalid`);
    for (const body of [
      { license: "CC-BY-4.0" },
      { license: "gpl" },
      { updateFrequency: "chaque-lundi" },
      { language: "klingon" },
      { temporalStart: "pas-une-date" },
    ]) {
      const r = await creator.send("PATCH", `/v1/collections/${id}`, body);
      expect(r.status, JSON.stringify(body)).toBe(422);
    }
  });

  test("effacement : licence '' et bornes temporelles null remettent les champs à vide", async () => {
    const { id } = await newCollection(`${tag}-meta-clear`);
    await creator.send("PATCH", `/v1/collections/${id}`, {
      license: "odbl-1.0",
      temporalStart: "2019-01-01",
      temporalEnd: "2019-02-01",
    });
    const cleared = await creator.send("PATCH", `/v1/collections/${id}`, {
      license: "",
      temporalStart: null,
      temporalEnd: null,
    });
    expect(cleared.status).toBe(200);
    expect(cleared.body).toMatchObject({ license: "", temporalStart: null, temporalEnd: null });
  });

  test("un lecteur ne peut pas modifier les métadonnées d'une collection publique (403/404)", async () => {
    const r = await reader.send("PATCH", `/v1/collections/${seed.collectionId}`, {
      license: "proprietary",
    });
    expect([403, 404]).toContain(r.status);
    const after = await creator.get(`/v1/collections/${seed.collectionId}`);
    expect(after.body.license).toBe("cc-by-4.0");
  });

  test("la licence propagée à DCAT est l'URI EU du catalogue ; « other » utilise licenseUri", async () => {
    const { id } = await newCollection(`${tag}-meta-other`);
    await creator.send("PATCH", `/v1/collections/${id}`, {
      isPublic: true,
      license: "other",
      licenseUri: "https://example.org/ma-licence",
    });
    const d = await anonGet(`/v1/dcat/datasets/${id}`);
    expect(d.body["dct:license"]["@id"]).toBe("https://example.org/ma-licence");
    const std = await anonGet(`/v1/dcat/datasets/${seed.collectionId}`);
    expect(std.body["dct:license"]["@id"]).toBe(
      "http://publications.europa.eu/resource/authority/licence/CC_BY",
    );
  });

  // Finding j07-014 : PATCH ne valide ni l'ordre des bornes temporelles ni le schéma de licenseUri.
  bug(
    "j07-014 : temporalEnd antérieure à temporalStart et licenseUri non http(s) sont refusées (422)",
    async () => {
      const { id } = await newCollection(`${tag}-meta-bad`);
      const order = await creator.send("PATCH", `/v1/collections/${id}`, {
        temporalStart: "2021-01-01",
        temporalEnd: "2020-01-01",
      });
      expect(order.status).toBe(422);
      const uri = await creator.send("PATCH", `/v1/collections/${id}`, {
        license: "other",
        licenseUri: "javascript:alert(1)",
      });
      expect(uri.status).toBe(422);
    },
  );
});

test.describe("j07 masquage de champ sensible", () => {
  const readers = () =>
    [
      ["creator", creator],
      ["analyst", analyst],
      ["reader", reader],
    ] as const;

  test("« pop » est masqué pour créateur, analyste, lecteur et anonyme sur OGC, item unique et STAC", async () => {
    const c = seed.collectionId;
    for (const [who, api] of readers()) {
      const list = await api.get(`/v1/collections/${c}/items?limit=2`);
      expect(list.body.features[0].properties, who).not.toHaveProperty("pop");
      const one = await api.get(`/v1/collections/${c}/items/2`);
      expect(one.body.properties, who).not.toHaveProperty("pop");
      const stac = await api.get(`/v1/stac/collections/${c}/items?limit=1`);
      expect(stac.body.features[0].properties, who).not.toHaveProperty("pop");
      const search = await api.get(`/v1/stac/search?collections=${c}&limit=1`);
      expect(search.body.features[0].properties, who).not.toHaveProperty("pop");
    }
    for (const p of [
      `/v1/collections/${c}/items?limit=1`,
      `/v1/collections/${c}/items/2`,
      `/v1/stac/collections/${c}/items/2`,
    ]) {
      const a = await anonGet(p);
      expect(JSON.stringify(a.body), p).not.toContain('"pop"');
    }
  });

  test("l'administrateur voit la valeur, et le champ ne sert pas d'oracle (filtre, agrégat) aux autres", async () => {
    const c = seed.collectionId;
    const adm = await admin.get(`/v1/collections/${c}/items/2`);
    expect(adm.body.properties.pop).toBeCloseTo(1000.5);
    for (const [who, api] of readers()) {
      const filter = await api.get(`/v1/collections/${c}/items?pop=1000.5`);
      expect(filter.status, `${who} filtre`).toBe(400);
      const agg = await api.send("POST", `/v1/collections/${c}/aggregate`, {
        measures: [{ op: "sum", field: "pop" }],
        groupBy: [],
      });
      expect(agg.status, `${who} agrégat`).toBe(400);
      const grp = await api.send("POST", `/v1/collections/${c}/aggregate`, {
        measures: [{ op: "count" }],
        groupBy: ["pop"],
      });
      expect(grp.status, `${who} groupBy`).toBe(400);
    }
  });

  test("déclarer un champ inconnu, réservé ou en double comme sensible est refusé", async () => {
    const { id } = await newCollection(`${tag}-sens-invalid`);
    for (const fields of [["inexistant"], ["id"], ["tenant_id"], ["geom"], ["secret", "secret"]]) {
      const r = await creator.send("PATCH", `/v1/collections/${id}`, { sensitiveFields: fields });
      expect([400, 422], JSON.stringify(fields)).toContain(r.status);
    }
  });

  test("cycle complet : déclarer puis retirer un champ sensible masque puis restitue la donnée", async () => {
    const { id, table } = await newCollection(`${tag}-sens-cycle`);
    await creator.send("PATCH", `/v1/collections/${id}`, { isPublic: true });
    // L'écriture REST d'une entité sur une collection vide échoue (j02-003) : insertion SQL directe.
    psql(
      `INSERT INTO ${table} (tenant_id, nom, secret, geom) VALUES ('default','a','S3CRET',ST_SetSRID(ST_MakePoint(2,48),4326))`,
    );
    await admin.send("PATCH", `/v1/collections/${id}`, { sensitiveFields: ["secret"] });
    expect(JSON.stringify((await anonGet(`/v1/collections/${id}/items`)).body)).not.toContain(
      "S3CRET",
    );
    await admin.send("PATCH", `/v1/collections/${id}`, { sensitiveFields: [] });
    expect(JSON.stringify((await anonGet(`/v1/collections/${id}/items`)).body)).toContain("S3CRET");
  });

  // Finding j07-015 : le schéma et la fiche collection exposent les noms des champs masqués.
  bug(
    "j07-015 : le schéma servi à un lecteur ou un anonyme ne liste pas le champ sensible",
    async () => {
      const anon = await anonGet(`/v1/collections/${seed.collectionId}/schema`);
      expect(anon.body.fields.map((f: any) => f.name)).not.toContain("pop");
      const rd = await reader.get(`/v1/collections/${seed.collectionId}`);
      expect(rd.body.sensitiveFields).toEqual([]);
    },
  );

  // Finding j07-016 : le propriétaire lui-même ne voit pas ses champs sensibles.
  bug(
    "j07-016 : le créateur propriétaire de la collection peut lire ses propres champs sensibles",
    async () => {
      const own = await creator.get(`/v1/collections/${seed.collectionId}/items/2`);
      expect(own.body.properties).toHaveProperty("pop");
    },
  );
});
