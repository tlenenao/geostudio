// SPDX-License-Identifier: Apache-2.0
// Déclencheurs automatiques (jsdom : `window`/`document`). Saisies sans pièce jointe : le clonage
// d'un Blob jsdom par fake-indexeddb n'est pas l'objet de ce fichier (cf. sync.test.ts, node).
import "fake-indexeddb/auto";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { DB_NAME, closeDb } from "./db";
import { enqueue } from "./outbox";
import { createSyncEngine, type SyncTransport } from "./sync";

const A = "t1:alice";
let n = 0;
const add = () =>
  enqueue(A, {
    opId: `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`,
    collectionId: "c",
    payload: { properties: {}, geometry: null },
  });

function counting() {
  const create = vi.fn(async () => ({ fid: "1" }));
  const transport: SyncTransport = { mode: "separate", create, uploadBlob: vi.fn() };
  return { create, transport };
}
const flush = () => new Promise((r) => setTimeout(r, 20));

beforeEach(async () => {
  await closeDb();
  await new Promise<void>((res) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
  });
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
});
afterEach(() => vi.restoreAllMocks());

test("start() synchronise tout de suite, puis à `online` et au retour au premier plan", async () => {
  const { create, transport } = counting();
  const engine = createSyncEngine({ ownerKey: A, transport, env: { locks: undefined } });
  await add();
  engine.start();
  await flush();
  expect(create).toHaveBeenCalledTimes(1); // passage initial

  await add();
  window.dispatchEvent(new Event("online"));
  await flush();
  expect(create).toHaveBeenCalledTimes(2);

  await add();
  Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
  await flush();
  expect(create).toHaveBeenCalledTimes(2); // en arrière-plan : rien
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
  await flush();
  expect(create).toHaveBeenCalledTimes(3);
  engine.stop();
});

test("stop() retire les écouteurs ; le déclenchement manuel reste possible", async () => {
  const { create, transport } = counting();
  const engine = createSyncEngine({ ownerKey: A, transport, env: { locks: undefined } });
  engine.start();
  await flush();
  engine.stop();
  await add();
  window.dispatchEvent(new Event("online"));
  await flush();
  expect(create).not.toHaveBeenCalled();
  expect((await engine.syncNow()).sent).toBe(1);
});

test("hors ligne au démarrage : pas de passage initial inutile", async () => {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  const { create, transport } = counting();
  await add();
  const engine = createSyncEngine({ ownerKey: A, transport, env: { locks: undefined } });
  engine.start();
  await flush();
  expect(create).not.toHaveBeenCalled();
  engine.stop();
});
