import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import {
  APP_CONFIG,
  apiFor,
  csvOfSize,
  deleteObject,
  psql,
  putObject,
  quotaApi,
  startQuotaCore,
  stopQuotaCore,
  waitQuotaCore,
  type Api,
} from "./helpers";

// Blocage par quota, sur un SECOND cœur (audit-core-quota, :8201) partageant la base et le
// S3 de la stack mais configuré avec des limites basses — la stack n'est pas modifiée.
test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);
const tag = stamp("j08b");
let admin: Api;
let creator: Api;
const keys: string[] = [];
let base: { items: number; collections: number; storage: number };
const STORAGE_HEADROOM = 5000;

test.beforeAll(async () => {
  const real = await apiFor("admin");
  const u = (await real.get("/v1/admin/usage")).body;
  base = { items: u.itemCount, collections: u.collectionCount, storage: u.storageBytes };
  startQuotaCore({
    items: base.items + 1,
    collections: base.collections,
    storage: base.storage + STORAGE_HEADROOM,
  });
  await waitQuotaCore();
  admin = quotaApi("admin");
  creator = quotaApi("creator");
});

test.afterAll(() => {
  stopQuotaCore();
  for (const k of keys) {
    try {
      deleteObject("S3_UPLOADS_BUCKET", k);
    } catch {
      /* déjà supprimé */
    }
  }
});

test("les limites du cœur de test sont exposées par GET /admin/usage et /me", async () => {
  const u = (await admin.get("/v1/admin/usage")).body;
  expect(u.maxItems).toBe(base.items + 1);
  expect(u.maxCollections).toBe(base.collections);
  expect(u.maxStorageBytes).toBe(base.storage + STORAGE_HEADROOM);
  const me = (await creator.get("/v1/me")).body;
  expect(me.capabilities.quotasEnabled).toBe(true);
  // Le créateur ne voit ni les comptes ni les limites : 403 sur la route d'usage.
  expect((await creator.get("/v1/admin/usage")).status).toBe(403);
});

// Sonde de concurrence : le contrôle est « compter puis insérer » sans verrou explicite ;
// 8 créations simultanées pour 1 place restante n'en ont accepté qu'une (pas de dépassement observé).
test("8 créations concurrentes avec 1 place restante n'en acceptent qu'une", async () => {
  const results = await Promise.all(
    Array.from({ length: 8 }, (_, i) =>
      creator.send("POST", "/v1/configs", { title: `${tag}-race-${i}`, config: APP_CONFIG }),
    ),
  );
  const created = results.filter((r) => r.status === 201).length;
  expect(created).toBeGreaterThanOrEqual(1);
  expect(created).toBe(1);
});

test("au quota d'items, POST /configs répond 409 RFC 7807 et la lecture reste possible", async () => {
  // Garantit le plafond quel que soit le résultat de la course précédente.
  for (let i = 0; i < 12; i++) {
    const r = await creator.send("POST", "/v1/configs", {
      title: `${tag}-fill-${i}`,
      config: APP_CONFIG,
    });
    if (r.status === 409) {
      expect(r.body.title).toBe("Conflict");
      expect(r.body.detail).toMatch(/quota d'items du tenant dépassé : \d+\/\d+/);
      break;
    }
    expect(r.status).toBe(201);
  }
  const blocked = await creator.send("POST", "/v1/configs", {
    title: `${tag}-x`,
    config: APP_CONFIG,
  });
  expect(blocked.status).toBe(409);
  // Même règle pour un administrateur.
  expect(
    (await admin.send("POST", "/v1/configs", { title: `${tag}-adm`, config: APP_CONFIG })).status,
  ).toBe(409);
  expect((await creator.get("/v1/items")).status).toBe(200);
});

test("au quota de collections, POST /collections/empty répond 409", async () => {
  const r = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-col`,
    columns: [],
  });
  expect(r.status).toBe(409);
  expect(r.body.detail).toMatch(/quota de collections du tenant dépassé/);
});

// Finding j08b-001 : POST /collections (enregistrement d'une table existante) ne vérifie pas le quota.
test("j08b-001 : enregistrer une table existante respecte le quota de collections", async () => {
  const t = `audj08b_reg_${Date.now().toString(36)}`;
  psql(`CREATE TABLE public.${t} (id serial primary key, geom geometry(Point,4326))`);
  const r = await admin.send("POST", "/v1/collections", { tableName: t, title: `${tag}-reg` });
  expect(r.status).toBe(409);
});

// Finding j08b-003 : l'objet déjà téléversé est compté deux fois (dans l'usage ET dans additional_bytes).
test("j08b-003 : un fichier de 3 Ko tient dans 5 Ko de marge de stockage", async () => {
  const pre = (await admin.get("/v1/admin/usage")).body.storageBytes;
  const fileSize = Buffer.byteLength(csvOfSize(3000));
  // Marge réelle suffisante : pre + fileSize <= limite tant que pre <= base + 5000 - fileSize.
  expect(pre + fileSize).toBeLessThanOrEqual(base.storage + STORAGE_HEADROOM);
  const key = putObject("S3_UPLOADS_BUCKET", "fits.csv", 3000);
  keys.push(key);
  const r = await creator.send("POST", "/v1/uploads", {
    key,
    filename: "fits.csv",
    collectionTitle: `${tag}-fits`,
    latField: "lat",
    lonField: "lon",
  });
  expect(r.status).not.toBe(409);
});

test("storage : un import plus gros que la limite est refusé en 413 avant création du job", async () => {
  const key = putObject("S3_UPLOADS_BUCKET", "overflow.csv", 8000);
  keys.push(key);
  const r = await creator.send("POST", "/v1/uploads", {
    key,
    filename: "overflow.csv",
    collectionTitle: `${tag}-overflow`,
    latField: "lat",
    lonField: "lon",
  });
  expect(r.status).toBe(413); // P26.09 : 413 pour le stockage, 409 pour un comptage
  expect(r.body.detail).toMatch(/quota de stockage du tenant dépassé/);
});

// Finding j08b-002 : un import refusé par le quota laisse son objet compté dans l'usage.
bug(
  "j08b-002 : après un refus de quota, le stockage compté revient à sa valeur d'avant",
  async () => {
    const before = (await admin.get("/v1/admin/usage")).body.storageBytes;
    const key = putObject("S3_UPLOADS_BUCKET", "overflow2.csv", 9000);
    keys.push(key);
    const r = await creator.send("POST", "/v1/uploads", {
      key,
      filename: "overflow2.csv",
      collectionTitle: `${tag}-overflow2`,
      latField: "lat",
      lonField: "lon",
    });
    expect(r.status).toBe(413);
    const after = (await admin.get("/v1/admin/usage")).body.storageBytes;
    // l'objet refusé n'est plus compté (≤ : le nettoyage asynchrone d'un import précédent peut aussi retirer des octets)
    expect(after).toBeLessThanOrEqual(before);
  },
);
