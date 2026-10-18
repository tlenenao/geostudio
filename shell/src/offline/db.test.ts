// @vitest-environment node
// SPDX-License-Identifier: Apache-2.0
// `fake-indexeddb` n'est importé qu'ici (jamais dans setup.ts : piège n°10). Environnement node :
// `Blob`/`File` y sont natifs et clonables par structuredClone, comme dans un vrai navigateur.
import "fake-indexeddb/auto";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CollectKit } from "../api/types";
import { DB_NAME, STORES, closeDb, getDb, openDb } from "./db";
import {
  KIT_MAX_AGE_MS,
  MAX_BLOB_BYTES,
  MAX_ENTRIES,
  MAX_PHOTOS_PER_ENTRY,
  OutboxLimitError,
  OutboxStorageError,
  SENT_KEEP_MS,
  deleteEntry,
  enqueue,
  getEntry,
  getKit,
  listBlobs,
  listEntries,
  markBlobUploaded,
  pendingCount,
  purgeExpired,
  purgeKits,
  putKit,
  updateEntry,
} from "./outbox";

const A = "t1:alice";
const B = "t1:bob";
const payload = { properties: { nom: "x" }, geometry: null };
const photo = (size = 10, name = "p.jpg") =>
  new File([new Uint8Array(size)], name, { type: "image/jpeg" });
const kit = (etag = "e1"): CollectKit => ({
  version: 1,
  title: "K",
  schema: { geometry: null, fields: [] },
  rules: [],
  geometryRequired: false,
  updatedAt: null,
  etag,
});
let n = 0;
const opId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;

beforeEach(async () => {
  await closeDb();
  await new Promise<void>((res, rej) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
    r.onerror = () => rej(r.error);
  });
});
afterEach(async () => {
  vi.restoreAllMocks();
  await closeDb();
});

test("la base expose les quatre stores", async () => {
  const db = await getDb();
  expect([...db.objectStoreNames].sort()).toEqual([...STORES].sort());
});

test("migration de version : les stores manquants sont créés, les données existantes gardées", async () => {
  // Une base « ancienne » à la version 1 qui n'a que `outbox`, avec une ligne.
  await new Promise<void>((res, rej) => {
    const r = indexedDB.open(DB_NAME, 1);
    r.onupgradeneeded = () => r.result.createObjectStore("outbox", { keyPath: "opId" });
    r.onsuccess = () => {
      const tx = r.result.transaction("outbox", "readwrite");
      tx.objectStore("outbox").put({ opId: "old", ownerKey: A, collectionId: "c" });
      tx.oncomplete = () => {
        r.result.close();
        res();
      };
    };
    r.onerror = () => rej(r.error);
  });
  const db = await openDb(2);
  expect([...db.objectStoreNames].sort()).toEqual([...STORES].sort());
  const row = await new Promise((res) => {
    const g = db.transaction("outbox").objectStore("outbox").get("old");
    g.onsuccess = () => res(g.result);
  });
  expect(row).toMatchObject({ opId: "old", ownerKey: A });
  db.close();
});

test("CRUD d'une saisie avec photos : les Blob sont stockés en Blob, jamais en base64", async () => {
  const id = opId();
  const e = await enqueue(A, {
    opId: id,
    collectionId: "c1",
    payload,
    blobs: [{ fieldKey: "photo", kind: "image", file: photo(5, "a.jpg") }],
  });
  expect(e).toMatchObject({ state: "queued", attempts: 0, ownerKey: A });
  const blobs = await listBlobs(A, id);
  expect(blobs).toHaveLength(1);
  expect(blobs[0].blob).toBeInstanceOf(Blob);
  expect(blobs[0]).toMatchObject({ name: "a.jpg", type: "image/jpeg", size: 5, uploaded: false });
  expect(blobs[0].clientOpId).toMatch(/^[0-9a-f-]{36}$/);

  await markBlobUploaded(A, blobs[0].blobId);
  expect((await listBlobs(A, id))[0].uploaded).toBe(true);

  const up = await updateEntry(A, id, { state: "needs_photos", attempts: 2, serverFid: "7" });
  expect(up).toMatchObject({ state: "needs_photos", attempts: 2, serverFid: "7" });
  expect(await listEntries(A)).toHaveLength(1);

  await deleteEntry(A, id);
  expect(await getEntry(A, id)).toBeUndefined();
  expect(await listBlobs(A, id)).toEqual([]);
});

test("isolation par ownerKey : un second utilisateur ne lit, ne modifie ni ne supprime rien", async () => {
  const id = opId();
  await enqueue(A, {
    opId: id,
    collectionId: "c",
    payload,
    blobs: [{ fieldKey: "p", kind: "image", file: photo() }],
  });
  expect(await listEntries(B)).toEqual([]);
  expect(await getEntry(B, id)).toBeUndefined();
  expect(await listBlobs(B, id)).toEqual([]);
  expect(await pendingCount(B)).toBe(0);
  expect(await updateEntry(B, id, { state: "failed_permanent" })).toBeUndefined();
  await deleteEntry(B, id);
  expect((await getEntry(A, id))?.state).toBe("queued");
  expect(await listBlobs(A, id)).toHaveLength(1);
  const [blob] = await listBlobs(A, id);
  await markBlobUploaded(B, blob.blobId);
  expect((await listBlobs(A, id))[0].uploaded).toBe(false);
});

test("plafond de 100 saisies par propriétaire ; les `sent` ne comptent pas ; l'autre propriétaire non plus", async () => {
  for (let i = 0; i < MAX_ENTRIES; i++)
    await enqueue(A, { opId: opId(), collectionId: "c", payload });
  await expect(enqueue(A, { opId: opId(), collectionId: "c", payload })).rejects.toMatchObject({
    name: "OutboxLimitError",
    code: "entries",
  });
  await enqueue(B, { opId: opId(), collectionId: "c", payload });
  const [first] = await listEntries(A);
  await updateEntry(A, first.opId, { state: "sent" });
  await enqueue(A, { opId: opId(), collectionId: "c", payload });
  // Remettre en file la même saisie (même opId) la remplace au lieu de la doubler.
  const second = (await listEntries(A)).find((e) => e.state !== "sent")!;
  await enqueue(A, { opId: second.opId, collectionId: "c", payload });
  expect((await listEntries(A)).filter((e) => e.state !== "sent")).toHaveLength(MAX_ENTRIES);
});

test("au plus 5 photos par saisie et 200 Mo de pièces jointes par propriétaire", async () => {
  const six = Array.from({ length: MAX_PHOTOS_PER_ENTRY + 1 }, (_, i) => ({
    fieldKey: `p${i}`,
    kind: "image" as const,
    file: photo(1),
  }));
  await expect(
    enqueue(A, { opId: opId(), collectionId: "c", payload, blobs: six }),
  ).rejects.toBeInstanceOf(OutboxLimitError);
  expect(await listEntries(A)).toEqual([]);

  // Taille annoncée par `size` : un faux fichier de 150 Mo suffit, sans allouer la mémoire.
  const big = (mb: number) => {
    const f = photo(1);
    Object.defineProperty(f, "size", { value: mb * 1024 * 1024 });
    return f;
  };
  await enqueue(A, {
    opId: opId(),
    collectionId: "c",
    payload,
    blobs: [{ fieldKey: "v", kind: "video", file: big(150) }],
  });
  await expect(
    enqueue(A, {
      opId: opId(),
      collectionId: "c",
      payload,
      blobs: [{ fieldKey: "v", kind: "video", file: big(60) }],
    }),
  ).rejects.toMatchObject({ code: "bytes" });
  expect(MAX_BLOB_BYTES).toBe(200 * 1024 * 1024);
  // L'autre propriétaire a son propre budget.
  await enqueue(B, {
    opId: opId(),
    collectionId: "c",
    payload,
    blobs: [{ fieldKey: "v", kind: "video", file: big(150) }],
  });
});

test("QuotaExceededError : erreur typée, aucune écriture partielle", async () => {
  const id = opId();
  const real = IDBObjectStore.prototype.put;
  vi.spyOn(IDBObjectStore.prototype, "put").mockImplementation(function (
    this: IDBObjectStore,
    v: unknown,
  ) {
    if (this.name === "outbox") throw new DOMException("full", "QuotaExceededError");
    return real.call(this, v);
  });
  await expect(
    enqueue(A, {
      opId: id,
      collectionId: "c",
      payload,
      blobs: [{ fieldKey: "p", kind: "image", file: photo() }],
    }),
  ).rejects.toBeInstanceOf(OutboxStorageError);
  vi.restoreAllMocks();
  expect(await listEntries(A)).toEqual([]);
  expect(await listBlobs(A, id)).toEqual([]); // le blob écrit avant l'échec a été annulé
});

test("les saisies `sent` sont purgées après 7 jours, pas avant ; les autres jamais", async () => {
  const t0 = 1_000_000;
  const sent = opId();
  const waiting = opId();
  await enqueue(A, { opId: sent, collectionId: "c", payload }, t0);
  await enqueue(A, { opId: waiting, collectionId: "c", payload }, t0);
  await updateEntry(A, sent, { state: "sent" }, t0);
  expect(await purgeExpired(A, t0 + SENT_KEEP_MS - 1)).toBe(0);
  expect(await purgeExpired(A, t0 + SENT_KEEP_MS + 1)).toBe(1);
  expect((await listEntries(A)).map((e) => e.opId)).toEqual([waiting]);
});

test("kits : isolés par propriétaire, périmés après 14 jours, purgés sans toucher la file", async () => {
  const t0 = 5_000_000;
  await putKit(A, `${A}:c1`, kit("e1"), t0);
  expect((await getKit(A, `${A}:c1`, t0 + 1))?.expired).toBe(false);
  expect((await getKit(A, `${A}:c1`, t0 + KIT_MAX_AGE_MS + 1))?.expired).toBe(true);
  expect(await getKit(B, `${A}:c1`, t0)).toBeUndefined();
  await enqueue(A, { opId: opId(), collectionId: "c1", payload });
  await purgeKits();
  expect(await getKit(A, `${A}:c1`, t0)).toBeUndefined();
  expect(await listEntries(A)).toHaveLength(1); // la file survit au logout
});
