// SPDX-License-Identifier: Apache-2.0
// L8 : moteur de synchronisation de la file de saisies (création seule, spec §4.3).
// Séquentiel (jamais deux envois en même temps pour un propriétaire, ni entre onglets), idempotent
// (`opId` = Idempotency-Key, un rejeu est inoffensif) et reprenable à la pièce jointe près.
import { decide } from "./decision";
import {
  deleteBlobsOf,
  listBlobs,
  listEntries,
  markBlobUploaded,
  purgeExpired,
  updateEntry,
} from "./outbox";
import type { BlobRecord, OutboxEntry } from "./db";

export type SyncTransport = {
  /**
   * `separate` : `create` ne porte que la saisie, les pièces jointes partent ensuite une par une
   * (utilisateur connecté : presign, PUT S3, confirm). `single` : `create` porte tout (page
   * publique : un seul POST multipart).
   */
  mode: "separate" | "single";
  create(
    entry: OutboxEntry,
    blobs: BlobRecord[],
    offlineCreatedAt: string,
  ): Promise<{ fid?: string }>;
  uploadBlob?(entry: OutboxEntry, fid: string, blob: BlobRecord): Promise<void>;
};

export type SyncSummary = {
  sent: number;
  conflicts: number;
  /** Saisies pas encore envoyées (hors `sent`) à la fin du passage. */
  remaining: number;
  /** `auth` : un 401 a mis la synchro en pause jusqu'à `resume()` (jeton à renouveler). */
  paused: "auth" | null;
  /** Prochaine échéance de réessai connue (ms epoch), ou `null`. */
  retryAt: number | null;
  /** Un autre onglet synchronise déjà : rien n'a été fait ici. */
  skipped?: boolean;
};

export type SyncEnv = {
  locks?: {
    request: (
      name: string,
      opts: object,
      cb: (lock: unknown) => Promise<unknown>,
    ) => Promise<unknown>;
  };
  now?: () => number;
};

const ACTIVE = new Set(["queued", "sending", "needs_photos"]);
const LOCK_NAME = "gs-sync";
const MAX_TIMER_MS = 15 * 60_000;

function toFile(b: BlobRecord): File {
  return new File([b.blob], b.name, { type: b.type });
}
export { toFile as blobToFile };

export function createSyncEngine(opts: {
  ownerKey: string;
  transport: SyncTransport;
  env?: SyncEnv;
  onChange?: (summary: SyncSummary) => void;
  onAuthRequired?: () => void;
}) {
  const { ownerKey, transport, onChange, onAuthRequired } = opts;
  const now = opts.env?.now ?? (() => Date.now());
  const locks =
    opts.env && "locks" in opts.env
      ? opts.env.locks
      : typeof navigator !== "undefined"
        ? (navigator as unknown as { locks?: SyncEnv["locks"] }).locks
        : undefined;
  let paused: "auth" | null = null;
  let running: Promise<SyncSummary> | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let started = false;
  const cleanups: (() => void)[] = [];

  async function sendOne(entry: OutboxEntry): Promise<"sent" | "conflict" | "retry" | "pause"> {
    const t = now();
    // `sending` n'est jamais un état d'arrivée durable : après un plantage, l'entrée est reprise.
    await updateEntry(ownerKey, entry.opId, { state: "sending" }, t);
    let fid = entry.serverFid;
    try {
      const blobs = await listBlobs(ownerKey, entry.opId);
      if (transport.mode === "separate") {
        if (!fid) {
          const created = await transport.create(
            entry,
            [],
            new Date(entry.createdAt).toISOString(),
          );
          fid = created.fid!;
          // Persisté AVANT les photos : une coupure ensuite ne recrée jamais la saisie.
          await updateEntry(ownerKey, entry.opId, { serverFid: fid, state: "needs_photos" }, now());
        }
        for (const blob of blobs.filter((b) => !b.uploaded)) {
          await transport.uploadBlob!(entry, fid, blob);
          await markBlobUploaded(ownerKey, blob.blobId); // persisté après CHAQUE confirm
        }
      } else {
        await transport.create(entry, blobs, new Date(entry.createdAt).toISOString());
      }
      await updateEntry(
        ownerKey,
        entry.opId,
        { state: "sent", lastError: null, lastDetail: undefined, fieldErrors: undefined },
        now(),
      );
      await deleteBlobsOf(ownerKey, entry.opId);
      return "sent";
    } catch (err) {
      const d = decide(err, entry.attempts);
      const resting = fid ? "needs_photos" : "queued";
      if (d.action === "pause_auth") {
        await updateEntry(ownerKey, entry.opId, { state: resting }, now());
        return "pause";
      }
      if (d.action === "retry") {
        await updateEntry(
          ownerKey,
          entry.opId,
          {
            state: resting,
            attempts: entry.attempts + 1,
            lastError: d.reason,
            lastDetail: d.detail,
            nextTryAt: now() + d.delayMs,
          },
          now(),
        );
        return "retry";
      }
      await updateEntry(
        ownerKey,
        entry.opId,
        {
          state: d.action === "conflict" ? "conflict" : "failed_permanent",
          attempts: entry.attempts + 1,
          lastError: d.reason,
          lastDetail: d.detail,
          fieldErrors: d.action === "conflict" ? d.errors : undefined,
        },
        now(),
      );
      return "conflict";
    }
  }

  async function pass(): Promise<SyncSummary> {
    const summary: SyncSummary = { sent: 0, conflicts: 0, remaining: 0, paused, retryAt: null };
    if (!paused) {
      await purgeExpired(ownerKey, now());
      for (const entry of await listEntries(ownerKey)) {
        if (!ACTIVE.has(entry.state) || entry.nextTryAt > now()) continue;
        const out = await sendOne(entry);
        if (out === "sent") summary.sent++;
        else if (out === "conflict") summary.conflicts++;
        else if (out === "pause") {
          paused = "auth";
          summary.paused = "auth";
          onAuthRequired?.();
          break;
        } else break; // réessai programmé : on s'arrête (réseau coupé ou serveur à ménager)
      }
    }
    const left = (await listEntries(ownerKey)).filter((e) => e.state !== "sent");
    summary.remaining = left.length;
    const waits = left.filter((e) => ACTIVE.has(e.state) && e.nextTryAt > now());
    summary.retryAt = waits.length ? Math.min(...waits.map((e) => e.nextTryAt)) : null;
    return summary;
  }

  function schedule(summary: SyncSummary) {
    if (timer) clearTimeout(timer);
    timer = null;
    if (!started || summary.retryAt === null || summary.paused) return;
    timer = setTimeout(
      () => void syncNow(),
      Math.min(MAX_TIMER_MS, Math.max(0, summary.retryAt - now())),
    );
  }

  /** Un passage ; des appels simultanés partagent le même (jamais deux envois en parallèle). */
  function syncNow(): Promise<SyncSummary> {
    running ??= (async () => {
      try {
        let summary: SyncSummary;
        if (locks) {
          let skipped = false;
          let out: SyncSummary | undefined;
          await locks.request(LOCK_NAME, { ifAvailable: true }, async (lock) => {
            if (!lock) {
              skipped = true;
              return;
            }
            out = await pass();
          });
          summary =
            skipped || !out
              ? { sent: 0, conflicts: 0, remaining: 0, paused, retryAt: null, skipped: true }
              : out;
        } else {
          summary = await pass();
        }
        onChange?.(summary);
        schedule(summary);
        return summary;
      } finally {
        running = null;
      }
    })();
    return running;
  }

  /** Après renouvellement du jeton : la file intacte repart. */
  function resume(): Promise<SyncSummary> {
    paused = null;
    return syncNow();
  }

  /** Déclencheurs automatiques : retour du réseau et retour au premier plan. */
  function start(): void {
    if (started) return;
    started = true;
    const onOnline = () => void syncNow();
    const onVisible = () => {
      if (document.visibilityState === "visible") void syncNow();
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    cleanups.push(
      () => window.removeEventListener("online", onOnline),
      () => document.removeEventListener("visibilitychange", onVisible),
    );
    if (navigator.onLine !== false) void syncNow();
  }

  function stop(): void {
    started = false;
    if (timer) clearTimeout(timer);
    timer = null;
    cleanups.splice(0).forEach((c) => c());
  }

  return { syncNow, resume, start, stop, isPaused: () => paused };
}

export type SyncEngine = ReturnType<typeof createSyncEngine>;
