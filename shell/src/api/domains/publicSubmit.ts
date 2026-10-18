// SPDX-License-Identifier: Apache-2.0
// L8 : soumission publique (ARC-10) depuis la page `/collect/:token`. Hors ItemClient : aucune
// session, jamais d'en-tête Authorization (le jeton du lien est dans le chemin).
import { solvePow } from "../../offline/pow";
import { fetchWithTimeout, parseErrorResponse } from "../base";
import type { CollectKit } from "../types";

export type PublicFile = { fieldKey: string; file: File };

export type PublicSubmission = {
  feature: { type: "Feature"; properties: Record<string, unknown>; geometry: unknown };
  files: PublicFile[];
  /** Identifiant d'idempotence : un rejeu du même envoi n'est jamais compté deux fois. */
  clientOpId: string;
  /** Piège à robots : toujours vide pour un humain. */
  honeypot?: string;
};

/** Kit public ; `null` si `etag` est toujours d'actualité (304). */
export async function fetchPublicKit(
  coreUrl: string,
  token: string,
  etag?: string,
): Promise<CollectKit | null> {
  const res = await fetchWithTimeout(
    `${coreUrl}/public/submit/${encodeURIComponent(token)}/kit`,
    etag ? { headers: { "If-None-Match": `"${etag}"` } } : {},
  );
  if (res.status === 304) return null;
  if (!res.ok) throw await parseErrorResponse(res);
  return (await res.json()) as CollectKit;
}

export async function submitPublic(
  coreUrl: string,
  token: string,
  sub: PublicSubmission,
  signal?: AbortSignal,
): Promise<void> {
  const base = `${coreUrl}/public/submit/${encodeURIComponent(token)}`;
  const form = new FormData();
  const ch = await fetchWithTimeout(`${base}/challenge`);
  if (!ch.ok) throw await parseErrorResponse(ch);
  const pow = (await ch.json()) as { challenge: string; bits: number; required: boolean };
  if (pow.required) {
    form.set("powChallenge", pow.challenge);
    form.set("powNonce", await solvePow(pow.challenge, pow.bits, { signal }));
  }
  form.set("payload", JSON.stringify(sub.feature));
  form.set("website", sub.honeypot ?? "");
  form.set("clientOpId", sub.clientOpId);
  for (const f of sub.files) {
    form.append("files", f.file, f.file.name);
    form.append("fieldKeys", f.fieldKey);
  }
  // Envoi de photos : plus long que le délai par défaut de 15 s (réseau de terrain).
  const res = await fetchWithTimeout(base, { method: "POST", body: form }, 120_000);
  if (!res.ok) throw await parseErrorResponse(res);
}
