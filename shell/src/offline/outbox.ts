// SPDX-License-Identifier: Apache-2.0
// L8 : file d'attente locale des saisies (création seule) et cache des kits de collecte.
// Règle d'isolation : TOUTE lecture et écriture est filtrée par `ownerKey` ; un autre utilisateur
// du même appareil ne voit, n'envoie ni ne modifie la file d'autrui.
import type { CollectKit } from "../api/types";
import { inTx, isQuotaError, wrap, type BlobRecord, type KitRecord, type OutboxEntry } from "./db";

export const MAX_ENTRIES = 100;
export const MAX_BLOB_BYTES = 200 * 1024 * 1024;
export const MAX_PHOTOS_PER_ENTRY = 5;
export const KIT_MAX_AGE_MS = 14 * 24 * 3600 * 1000;
export const SENT_KEEP_MS = 7 * 24 * 3600 * 1000;

/** Refus explicite de mise en file : l'appelant garde le formulaire ouvert. */
export class OutboxLimitError extends Error {
  constructor(readonly code: "entries" | "bytes" | "photos") {
    super(`outbox limit: ${code}`);
    this.name = "OutboxLimitError";
  }
}

/** Le navigateur n'a plus de place : rien n'a été écrit (transaction annulée). */
export class OutboxStorageError extends Error {
  constructor() {
    super("local storage quota exceeded");
    this.name = "OutboxStorageError";
  }
}

export type NewEntry = {
  opId: string;
  collectionId: string;
  payload: OutboxEntry["payload"];
  blobs?: { fieldKey: string; kind: BlobRecord["kind"]; file: File }[];
};

const mine = <T extends { ownerKey: string }>(rows: T[], ownerKey: string): T[] =>
  rows.filter((r) => r.ownerKey === ownerKey);

async function allEntries(tx: IDBTransaction, ownerKey: string): Promise<OutboxEntry[]> {
  const rows = await wrap(tx.objectStore("outbox").index("ownerKey").getAll(ownerKey));
  return mine(rows as OutboxEntry[], ownerKey); // ceinture et bretelles : le filtre est aussi ici
}

export async function enqueue(
  ownerKey: string,
  entry: NewEntry,
  now = Date.now(),
): Promise<OutboxEntry> {
  const blobs = entry.blobs ?? [];
  if (blobs.length > MAX_PHOTOS_PER_ENTRY) throw new OutboxLimitError("photos");
  const row: OutboxEntry = {
    opId: entry.opId,
    ownerKey,
    collectionId: entry.collectionId,
    kind: "feature",
    payload: entry.payload,
    createdAt: now,
    updatedAt: now,
    state: "queued",
    attempts: 0,
    lastError: null,
    nextTryAt: 0,
  };
  try {
    await inTx(["outbox", "blobs"], "readwrite", async (tx) => {
      const existing = await allEntries(tx, ownerKey);
      // Une même saisie remise en file (même opId) remplace l'ancienne : pas de doublon.
      const others = existing.filter((e) => e.opId !== row.opId && e.state !== "sent");
      if (others.length >= MAX_ENTRIES) throw new OutboxLimitError("entries");
      const stored = mine(
        (await wrap(tx.objectStore("blobs").index("ownerKey").getAll(ownerKey))) as BlobRecord[],
        ownerKey,
      ).filter((b) => b.opId !== row.opId);
      const used = stored.reduce((n, b) => n + b.size, 0);
      if (used + blobs.reduce((n, b) => n + b.file.size, 0) > MAX_BLOB_BYTES)
        throw new OutboxLimitError("bytes");
      const store = tx.objectStore("blobs");
      for (const old of await wrap(store.index("opId").getAll(row.opId)))
        if ((old as BlobRecord).ownerKey === ownerKey) store.delete((old as BlobRecord).blobId);
      for (const b of blobs) {
        const rec: BlobRecord = {
          blobId: crypto.randomUUID(),
          opId: row.opId,
          ownerKey,
          fieldKey: b.fieldKey,
          kind: b.kind,
          name: b.file.name,
          type: b.file.type || "application/octet-stream",
          size: b.file.size,
          blob: b.file,
          clientOpId: crypto.randomUUID(),
          uploaded: false,
        };
        store.put(rec);
      }
      tx.objectStore("outbox").put(row);
    });
  } catch (err) {
    if (isQuotaError(err)) throw new OutboxStorageError();
    throw err;
  }
  return row;
}

export async function listEntries(ownerKey: string): Promise<OutboxEntry[]> {
  const rows = await inTx(["outbox"], "readonly", (tx) => allEntries(tx, ownerKey));
  return rows.sort((a, b) => a.createdAt - b.createdAt);
}

export async function getEntry(ownerKey: string, opId: string): Promise<OutboxEntry | undefined> {
  const row = await inTx(["outbox"], "readonly", (tx) => wrap(tx.objectStore("outbox").get(opId)));
  return row && (row as OutboxEntry).ownerKey === ownerKey ? (row as OutboxEntry) : undefined;
}

export type EntryPatch = Partial<
  Pick<
    OutboxEntry,
    "payload" | "state" | "attempts" | "lastError" | "fieldErrors" | "nextTryAt" | "serverFid"
  >
>;

/** Met à jour une entrée du propriétaire ; `undefined` si elle n'existe pas ou n'est pas à lui. */
export async function updateEntry(
  ownerKey: string,
  opId: string,
  patch: EntryPatch,
  now = Date.now(),
): Promise<OutboxEntry | undefined> {
  return inTx(["outbox"], "readwrite", async (tx) => {
    const store = tx.objectStore("outbox");
    const cur = (await wrap(store.get(opId))) as OutboxEntry | undefined;
    if (!cur || cur.ownerKey !== ownerKey) return undefined;
    const next: OutboxEntry = { ...cur, ...patch, updatedAt: now };
    store.put(next);
    return next;
  });
}

export async function deleteEntry(ownerKey: string, opId: string): Promise<void> {
  await inTx(["outbox", "blobs"], "readwrite", async (tx) => {
    const cur = (await wrap(tx.objectStore("outbox").get(opId))) as OutboxEntry | undefined;
    if (!cur || cur.ownerKey !== ownerKey) return;
    const blobs = tx.objectStore("blobs");
    for (const b of (await wrap(blobs.index("opId").getAll(opId))) as BlobRecord[])
      if (b.ownerKey === ownerKey) blobs.delete(b.blobId);
    tx.objectStore("outbox").delete(opId);
  });
}

export async function listBlobs(ownerKey: string, opId: string): Promise<BlobRecord[]> {
  const rows = await inTx(["blobs"], "readonly", (tx) =>
    wrap(tx.objectStore("blobs").index("opId").getAll(opId)),
  );
  return mine(rows as BlobRecord[], ownerKey);
}

/** Pièce jointe confirmée par le serveur : persisté avant de passer à la suivante (reprise exacte). */
export async function markBlobUploaded(ownerKey: string, blobId: string): Promise<void> {
  await inTx(["blobs"], "readwrite", async (tx) => {
    const store = tx.objectStore("blobs");
    const cur = (await wrap(store.get(blobId))) as BlobRecord | undefined;
    if (cur && cur.ownerKey === ownerKey) store.put({ ...cur, uploaded: true });
  });
}

/** Libère les `Blob` d'une saisie envoyée : l'historique `sent` n'a plus besoin des fichiers. */
export async function deleteBlobsOf(ownerKey: string, opId: string): Promise<void> {
  await inTx(["blobs"], "readwrite", async (tx) => {
    const store = tx.objectStore("blobs");
    for (const b of (await wrap(store.index("opId").getAll(opId))) as BlobRecord[])
      if (b.ownerKey === ownerKey) store.delete(b.blobId);
  });
}

/** Saisies qui attendent encore d'être envoyées (tout sauf `sent`). */
export async function pendingCount(ownerKey: string): Promise<number> {
  return (await listEntries(ownerKey)).filter((e) => e.state !== "sent").length;
}

export async function purgeExpired(ownerKey: string, now = Date.now()): Promise<number> {
  const old = (await listEntries(ownerKey)).filter(
    (e) => e.state === "sent" && now - e.updatedAt > SENT_KEEP_MS,
  );
  for (const e of old) await deleteEntry(ownerKey, e.opId);
  return old.length;
}

// --------------------------------------------------------------------------- kits

export async function putKit(
  ownerKey: string,
  key: string,
  kit: CollectKit,
  now = Date.now(),
): Promise<void> {
  const rec: KitRecord = { key, ownerKey, kit, fetchedAt: now, etag: kit.etag };
  await inTx(["kits"], "readwrite", async (tx) => {
    tx.objectStore("kits").put(rec);
  });
}

/** Kit en cache ; `expired` (> 14 j) n'empêche pas de lire, l'appelant avertit. */
export async function getKit(
  ownerKey: string,
  key: string,
  now = Date.now(),
): Promise<(KitRecord & { expired: boolean }) | undefined> {
  const rec = (await inTx(["kits"], "readonly", (tx) => wrap(tx.objectStore("kits").get(key)))) as
    KitRecord | undefined;
  if (!rec || rec.ownerKey !== ownerKey) return undefined;
  return { ...rec, expired: now - rec.fetchedAt > KIT_MAX_AGE_MS };
}

/** Kit revalidé par un 304 : seule la date de fraîcheur avance, le contenu n'est pas réécrit. */
export async function touchKit(ownerKey: string, key: string, now = Date.now()): Promise<void> {
  await inTx(["kits"], "readwrite", async (tx) => {
    const store = tx.objectStore("kits");
    const rec = (await wrap(store.get(key))) as KitRecord | undefined;
    if (rec && rec.ownerKey === ownerKey) store.put({ ...rec, fetchedAt: now });
  });
}

/** Déconnexion : les kits partent, la file reste (perdre des saisies de terrain est pire). */
export async function purgeKits(): Promise<void> {
  await inTx(["kits"], "readwrite", async (tx) => {
    tx.objectStore("kits").clear();
  });
}
