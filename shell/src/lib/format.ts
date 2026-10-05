// SPDX-License-Identifier: Apache-2.0
// Formats d'affichage fr-FR, indépendants de la locale du navigateur (P34.10/13/21).

/** Fuseau d'affichage unique (REV-285 g) : seule la locale était fixée, pas le fuseau. */
export const APP_TIME_ZONE = "Europe/Paris";

// REV-285(g) : une valeur absente ou non finie s'affiche « — », jamais « NaN »,
// « ∞ » ni le 01/01/1970 de `new Date(null)`.
const MISSING = "—";

/** Date + heure « 30/09/2026 04:52:57 » ; l'entrée illisible est rendue telle quelle. */
export function formatDateTime(iso: string | number | Date | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return MISSING;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString("fr-FR", { timeZone: APP_TIME_ZONE });
}

/** Nombre fr-FR (« 1 234 567,75 ») ; au plus `maxDecimals` décimales (2 par défaut). */
export function formatNumber(
  n: number | null | undefined,
  maxDecimals = 2,
  minDecimals = 0,
): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return MISSING;
  return n.toLocaleString("fr-FR", {
    maximumFractionDigits: maxDecimals,
    minimumFractionDigits: minDecimals,
  });
}

/** Taille en octets lisible (« 3 Ko », « 1,5 Mo ») : unité adaptée, séparateur décimal fr. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return MISSING;
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${formatNumber(value, i === 0 ? 0 : 1)} ${units[i]}`;
}
