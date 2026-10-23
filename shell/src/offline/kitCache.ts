// SPDX-License-Identifier: Apache-2.0
// L8 : kit de collecte en cache local. En ligne : revalidation `If-None-Match` (304 = rien à
// réécrire) ; hors ligne : dernier kit connu ; jamais chargé et hors ligne : erreur explicite.
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import type { CollectKit } from "../api/types";
import { getKit, putKit, touchKit } from "./outbox";

export type KitResult = {
  kit: CollectKit;
  /** Servi depuis le cache faute de réseau (le serveur n'a pas pu confirmer qu'il est à jour). */
  fromCache: boolean;
  /** Vieux de plus de 14 jours : avertissement non bloquant, les saisies en file restent valides. */
  expired: boolean;
};

/** Hors ligne et aucun kit sur cet appareil : le formulaire ne peut pas être construit. */
export class KitUnavailableError extends Error {
  constructor() {
    super("collect kit unavailable offline");
    this.name = "KitUnavailableError";
  }
}

/** `fetcher(etag)` renvoie le kit, ou `null` si l'ETag fourni est toujours d'actualité (304). */
export type KitFetcher = (etag?: string) => Promise<CollectKit | null>;

// Un IndexedDB indisponible (navigation privée, stockage bloqué) ne doit jamais empêcher la saisie
// en ligne : le cache est un confort, pas une condition.
async function safely<T>(run: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await run();
  } catch {
    return fallback;
  }
}

export async function loadKit(
  ownerKey: string,
  key: string,
  fetcher: KitFetcher,
  now = Date.now(),
): Promise<KitResult> {
  const cached = await safely(() => getKit(ownerKey, key, now), undefined);
  let fresh: CollectKit | null;
  try {
    fresh = await fetcher(cached?.etag);
  } catch (err) {
    if (!(err instanceof CoreUnreachableError)) throw err; // 403/404/410… : réponse réelle du serveur
    if (!cached) throw new KitUnavailableError();
    return { kit: cached.kit, fromCache: true, expired: cached.expired };
  }
  if (fresh === null) {
    if (!cached) throw new Error("304 sans kit en cache");
    await safely(() => touchKit(ownerKey, key, now), undefined);
    return { kit: cached.kit, fromCache: false, expired: false };
  }
  await safely(() => putKit(ownerKey, key, fresh, now), undefined);
  return { kit: fresh, fromCache: false, expired: false };
}
