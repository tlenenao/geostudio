// SPDX-License-Identifier: Apache-2.0
// L8 : base IndexedDB de la collecte hors-ligne (`gs-collect-v1`). Wrapper natif minimal, sans
// dépendance. Quatre stores : `kits` (schémas en cache), `outbox` (saisies à envoyer), `blobs`
// (pièces jointes, stockées en `Blob`, jamais en base64) et `meta`.
import type { CollectKit } from "../api/types";

export const DB_NAME = "gs-collect-v1";
export const DB_VERSION = 1;

export type OutboxState =
  "queued" | "sending" | "needs_photos" | "sent" | "conflict" | "failed_permanent";

export type FieldProblem = { field: string; code: string; message: string };

export type OutboxEntry = {
  /** UUID v4 créé à l'ouverture du brouillon : sert d'`Idempotency-Key` / `clientOpId`. */
  opId: string;
  /** `tenant:sub` (utilisateur connecté) ou `public:<jeton>` : toute lecture est filtrée dessus. */
  ownerKey: string;
  collectionId: string;
  kind: "feature";
  payload: { properties: Record<string, unknown>; geometry: unknown };
  createdAt: number;
  updatedAt: number;
  state: OutboxState;
  attempts: number;
  lastError: string | null;
  fieldErrors?: FieldProblem[];
  nextTryAt: number;
  serverFid?: string;
};

export type BlobRecord = {
  blobId: string;
  opId: string;
  ownerKey: string;
  fieldKey: string;
  kind: "image" | "audio" | "video" | "file";
  name: string;
  type: string;
  size: number;
  blob: Blob;
  /** `Idempotency-Key` de la confirmation de cette pièce jointe. */
  clientOpId: string;
  uploaded: boolean;
};

export type KitRecord = {
  /** `${tenantId}:${sub}:${collectionId}` ou `public:<jeton>`. */
  key: string;
  ownerKey: string;
  kit: CollectKit;
  fetchedAt: number;
  etag: string;
};

export const STORES = ["kits", "outbox", "blobs", "meta"] as const;
export type StoreName = (typeof STORES)[number];

/** Crée les stores manquants sans toucher aux données existantes (migration additive). */
function upgrade(db: IDBDatabase): void {
  if (!db.objectStoreNames.contains("kits")) {
    db.createObjectStore("kits", { keyPath: "key" }).createIndex("ownerKey", "ownerKey");
  }
  if (!db.objectStoreNames.contains("outbox")) {
    db.createObjectStore("outbox", { keyPath: "opId" }).createIndex("ownerKey", "ownerKey");
  }
  if (!db.objectStoreNames.contains("blobs")) {
    const blobs = db.createObjectStore("blobs", { keyPath: "blobId" });
    blobs.createIndex("opId", "opId");
    blobs.createIndex("ownerKey", "ownerKey");
  }
  if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
}

export function openDb(
  version = DB_VERSION,
  factory: IDBFactory = indexedDB,
): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(DB_NAME, version);
    req.onupgradeneeded = () => upgrade(req.result);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () =>
      reject(new DOMException("base verrouillée par un autre onglet", "InvalidStateError"));
  });
}

let cached: Promise<IDBDatabase> | null = null;

/** Connexion partagée du module ; une connexion fermée de l'extérieur est rouverte. */
export function getDb(): Promise<IDBDatabase> {
  cached ??= openDb().then((db) => {
    db.onclose = () => (cached = null);
    db.onversionchange = () => {
      db.close();
      cached = null;
    };
    return db;
  });
  return cached;
}

export async function closeDb(): Promise<void> {
  const p = cached;
  cached = null;
  if (p) (await p).close();
}

export function wrap<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Résout quand la transaction est validée ; rejette si elle est annulée (quota compris). */
export function committed(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new DOMException("transaction annulée", "AbortError"));
  });
}

/** Exécute `fn` dans une transaction ; `fn` ne doit attendre que des requêtes IndexedDB. */
export async function inTx<T>(
  stores: StoreName[],
  mode: IDBTransactionMode,
  fn: (tx: IDBTransaction) => Promise<T>,
): Promise<T> {
  const db = await getDb();
  const tx = db.transaction(stores, mode);
  const finished = committed(tx);
  try {
    const out = await fn(tx);
    await finished;
    return out;
  } catch (err) {
    try {
      tx.abort();
    } catch {
      // déjà terminée
    }
    await finished.catch(() => undefined);
    throw err;
  }
}

export function isQuotaError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "QuotaExceededError";
}
