// @vitest-environment node
// SPDX-License-Identifier: Apache-2.0
import "fake-indexeddb/auto";
import { beforeEach, expect, test, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { DB_NAME, closeDb, type BlobRecord, type OutboxEntry } from "./db";
import { enqueue, getEntry, listBlobs, listEntries } from "./outbox";
import { createSyncEngine, type SyncEnv, type SyncTransport } from "./sync";

const A = "t1:alice";
const clock = { t: 1_000_000 };
const env: SyncEnv = { locks: undefined, now: () => clock.t };
const photo = (name: string) => new File([new Uint8Array(4)], name, { type: "image/jpeg" });
let n = 0;
const opId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;
const add = (props: Record<string, unknown> = {}, files: string[] = [], owner = A) =>
  enqueue(
    owner,
    {
      opId: opId(),
      collectionId: "c1",
      payload: { properties: props, geometry: null },
      blobs: files.map((f, i) => ({ fieldKey: `p${i}`, kind: "image" as const, file: photo(f) })),
    },
    clock.t++,
  );

/** Serveur simulé : dédoublonne sur la clé d'idempotence (comme `collect_client_ops`). */
function fakeServer(opts: { dedupe?: boolean } = {}) {
  const rows = new Map<string, string>();
  let seq = 0;
  const log: string[] = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const confirmed: string[] = [];
  const hooks = {
    failCreate: null as null | (() => unknown),
    failUpload: null as null | ((b: BlobRecord) => unknown),
    lostResponse: false,
  };
  const transport: SyncTransport = {
    mode: "separate",
    async create(entry: OutboxEntry) {
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      try {
        const failure = hooks.failCreate?.();
        if (failure) throw failure;
        const key = opts.dedupe === false ? `${entry.opId}-${++seq}` : entry.opId;
        if (!rows.has(key)) rows.set(key, String(++seq));
        log.push(`create:${entry.opId}`);
        if (hooks.lostResponse) {
          hooks.lostResponse = false;
          throw new CoreUnreachableError(); // créée côté serveur, réponse perdue
        }
        return { fid: rows.get(key)! };
      } finally {
        inFlight--;
      }
    },
    async uploadBlob(_entry, _fid, blob) {
      if (hooks.failUpload) {
        const e = hooks.failUpload(blob);
        if (e) throw e;
      }
      confirmed.push(blob.name);
      log.push(`confirm:${blob.name}`);
    },
  };
  return { rows, log, transport, hooks, confirmed, maxInFlight: () => maxInFlight };
}

beforeEach(async () => {
  clock.t = 1_000_000;
  await closeDb();
  await new Promise<void>((res) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
  });
});

test("envoie les saisies dans l'ordre de création, marque `sent` et libère les fichiers", async () => {
  const s = fakeServer();
  const e1 = await add({ nom: "1" }, ["a.jpg"]);
  const e2 = await add({ nom: "2" });
  const out = await createSyncEngine({ ownerKey: A, transport: s.transport, env }).syncNow();
  expect(out).toMatchObject({ sent: 2, conflicts: 0, remaining: 0, paused: null });
  expect(s.log).toEqual([`create:${e1.opId}`, "confirm:a.jpg", `create:${e2.opId}`]);
  expect((await listEntries(A)).map((e) => e.state)).toEqual(["sent", "sent"]);
  expect(await listBlobs(A, e1.opId)).toEqual([]);
});

test("reprise après coupure entre la création et la 2e photo : ni doublon ni photo renvoyée", async () => {
  const s = fakeServer();
  const e = await add({ nom: "x" }, ["a.jpg", "b.jpg"]);
  s.hooks.failUpload = (b) => (b.name === "b.jpg" ? new CoreUnreachableError() : null);
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  const first = await engine.syncNow();
  expect(first).toMatchObject({ sent: 0, remaining: 1 });
  const mid = (await getEntry(A, e.opId))!;
  expect(mid).toMatchObject({ state: "needs_photos", serverFid: "1", lastError: "network" });
  expect((await listBlobs(A, e.opId)).map((b) => [b.name, b.uploaded])).toEqual([
    ["a.jpg", true],
    ["b.jpg", false],
  ]);
  // Le réseau revient ; l'échéance de réessai est passée.
  s.hooks.failUpload = null;
  clock.t = mid.nextTryAt + 1;
  const second = await engine.syncNow();
  expect(second.sent).toBe(1);
  expect(s.rows.size).toBe(1);
  expect(s.log.filter((l) => l.startsWith("create"))).toHaveLength(1);
  expect(s.confirmed).toEqual(["a.jpg", "b.jpg"]); // a.jpg une seule fois
});

test("réponse perdue après création côté serveur : le rejeu (même clé) ne crée pas de doublon", async () => {
  const s = fakeServer();
  const e = await add({ nom: "x" });
  s.hooks.lostResponse = true;
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  await engine.syncNow();
  expect((await getEntry(A, e.opId))?.state).toBe("queued");
  clock.t += 10 * 60_000;
  await engine.syncNow();
  expect((await getEntry(A, e.opId))?.state).toBe("sent");
  expect(s.rows.size).toBe(1);
});

test("backoff exponentiel et Retry-After : pas de réessai avant l'échéance", async () => {
  const s = fakeServer();
  const e = await add();
  s.hooks.failCreate = () => new ApiError(429, { retryAfter: 90 });
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  const t0 = clock.t;
  const out = await engine.syncNow();
  expect(out.retryAt).toBe(t0 + 90_000);
  expect(await getEntry(A, e.opId)).toMatchObject({
    state: "queued",
    attempts: 1,
    lastError: "rate_limited",
  });
  s.hooks.failCreate = null;
  clock.t = t0 + 89_000;
  expect((await engine.syncNow()).sent).toBe(0); // trop tôt
  clock.t = t0 + 90_001;
  expect((await engine.syncNow()).sent).toBe(1);
});

test("401 : pause globale, file intacte, rien n'est envoyé tant qu'on n'a pas repris", async () => {
  const s = fakeServer();
  const e = await add();
  s.hooks.failCreate = () => new ApiError(401);
  const onAuth = vi.fn();
  const engine = createSyncEngine({
    ownerKey: A,
    transport: s.transport,
    env,
    onAuthRequired: onAuth,
  });
  expect(await engine.syncNow()).toMatchObject({ paused: "auth", remaining: 1 });
  expect(onAuth).toHaveBeenCalledTimes(1);
  expect(await getEntry(A, e.opId)).toMatchObject({ state: "queued", attempts: 0 });
  s.hooks.failCreate = null;
  await engine.syncNow();
  expect(s.rows.size).toBe(0); // toujours en pause
  expect(engine.isPaused()).toBe("auth");
  expect((await engine.resume()).sent).toBe(1);
  expect(s.rows.size).toBe(1);
});

test("422 : conflit avec les erreurs de champ, jamais rejoué ; les saisies suivantes partent", async () => {
  const s = fakeServer();
  const bad = await add({ nom: "" });
  const good = await add({ nom: "ok" });
  const errors = [{ field: "nom", code: "required", message: "obligatoire" }];
  let first = true;
  s.hooks.failCreate = () => {
    if (first) {
      first = false;
      return new ApiError(422, { errors });
    }
    return null;
  };
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  expect(await engine.syncNow()).toMatchObject({ sent: 1, conflicts: 1 });
  expect(await getEntry(A, bad.opId)).toMatchObject({
    state: "conflict",
    lastError: "invalid",
    fieldErrors: errors,
  });
  expect((await getEntry(A, good.opId))?.state).toBe("sent");
  await engine.syncNow();
  expect(s.log.filter((l) => l === `create:${bad.opId}`)).toHaveLength(0); // jamais rejoué
});

test("séquentiel : des déclenchements simultanés partagent un seul passage, jamais deux envois en parallèle", async () => {
  const s = fakeServer();
  await add({ a: 1 });
  await add({ a: 2 });
  await add({ a: 3 });
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  const [r1, r2, r3] = await Promise.all([engine.syncNow(), engine.syncNow(), engine.syncNow()]);
  expect(r1).toBe(r2);
  expect(r2).toBe(r3);
  expect(s.maxInFlight()).toBe(1);
  expect(s.rows.size).toBe(3);
});

test("verrou multi-onglets : si un autre onglet tient `gs-sync`, rien n'est envoyé ici", async () => {
  const s = fakeServer();
  await add();
  const request = vi.fn(async (_n: string, _o: object, cb: (l: unknown) => Promise<unknown>) =>
    cb(null),
  );
  const busy = createSyncEngine({
    ownerKey: A,
    transport: s.transport,
    env: { ...env, locks: { request } },
  });
  expect(await busy.syncNow()).toMatchObject({ skipped: true, sent: 0 });
  expect(request).toHaveBeenCalledWith("gs-sync", { ifAvailable: true }, expect.any(Function));
  expect(s.rows.size).toBe(0);
  const free = createSyncEngine({
    ownerKey: A,
    transport: s.transport,
    env: { ...env, locks: { request: async (_n, _o, cb) => cb({ name: "gs-sync" }) } },
  });
  expect((await free.syncNow()).sent).toBe(1);
});

test("isolation : le moteur d'un propriétaire n'envoie jamais la file d'un autre", async () => {
  const s = fakeServer();
  await add({ mine: true });
  await add({ theirs: true }, [], "t1:bob");
  await createSyncEngine({ ownerKey: A, transport: s.transport, env }).syncNow();
  expect(s.rows.size).toBe(1);
  expect((await listEntries("t1:bob"))[0].state).toBe("queued");
});

test("mode public (`single`) : saisie et fichiers partent dans un seul appel, clé = opId", async () => {
  const calls: { opId: string; files: string[] }[] = [];
  const transport: SyncTransport = {
    mode: "single",
    async create(entry, blobs) {
      calls.push({ opId: entry.opId, files: blobs.map((b) => b.name) });
      return {};
    },
  };
  const e = await add({ nom: "x" }, ["a.jpg", "b.jpg"], "public:tok");
  const out = await createSyncEngine({ ownerKey: "public:tok", transport, env }).syncNow();
  expect(out.sent).toBe(1);
  expect(calls).toEqual([{ opId: e.opId, files: ["a.jpg", "b.jpg"] }]);
  expect(await listBlobs("public:tok", e.opId)).toEqual([]);
});

test("quota de jeton public épuisé : échec définitif, pas de réessai", async () => {
  const s = fakeServer();
  const e = await add();
  s.hooks.failCreate = () => new ApiError(429, { detail: "submission quota exhausted" });
  const engine = createSyncEngine({ ownerKey: A, transport: s.transport, env });
  await engine.syncNow();
  expect(await getEntry(A, e.opId)).toMatchObject({
    state: "failed_permanent",
    lastError: "quota",
  });
  expect((await engine.syncNow()).retryAt).toBeNull();
});
