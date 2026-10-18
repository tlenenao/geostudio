// SPDX-License-Identifier: Apache-2.0
// Formats d'affichage : seul point où une locale `Intl` ou un fuseau est nommé (AUD-115,
// règle ESLint `no-restricted-syntax` sur les littéraux "fr-FR"/"Europe/Paris" ailleurs).
// La locale suit la langue active de l'interface (i18n), le fuseau une préférence.
import { getLocale } from "../i18n";

const TZ_STORAGE_KEY = "gs.timeZone";
const DEFAULT_TIME_ZONE = "Europe/Paris";

/** Locale `Intl` de la langue d'interface active (BCP 47 régionalisé). */
export function intlLocale(): string {
  return getLocale() === "en" ? "en-GB" : "fr-FR";
}

/** Fuseau d'affichage : préférence stockée (IANA valide) sinon Europe/Paris. */
export function getTimeZone(): string {
  try {
    const stored = localStorage.getItem(TZ_STORAGE_KEY);
    if (stored) {
      new Intl.DateTimeFormat(undefined, { timeZone: stored }); // lève si non IANA
      return stored;
    }
  } catch {
    /* stockage indisponible ou fuseau invalide : défaut */
  }
  return DEFAULT_TIME_ZONE;
}

// Formateurs créés à la demande (la locale peut changer entre deux appels) et mis en cache.
const numberCache = new Map<string, Intl.NumberFormat>();
const dateCache = new Map<string, Intl.DateTimeFormat>();

/** `Intl.NumberFormat` dans la locale active. */
export function numberFormat(options: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const key = `${intlLocale()}|${JSON.stringify(options)}`;
  let f = numberCache.get(key);
  if (!f) numberCache.set(key, (f = new Intl.NumberFormat(intlLocale(), options)));
  return f;
}

/** `Intl.DateTimeFormat` dans la locale active (fuseau explicite via `options.timeZone`). */
export function dateFormat(options: Intl.DateTimeFormatOptions = {}): Intl.DateTimeFormat {
  const key = `${intlLocale()}|${JSON.stringify(options)}`;
  let f = dateCache.get(key);
  if (!f) dateCache.set(key, (f = new Intl.DateTimeFormat(intlLocale(), options)));
  return f;
}

/** Comparaison de textes : accents et chiffres respectés (« Étage » avant « Zone »). */
export function compareText(a: string, b: string): number {
  return a.localeCompare(b, intlLocale(), { numeric: true, sensitivity: "base" });
}

// REV-285(g) : une valeur absente ou non finie s'affiche « — », jamais « NaN »,
// « ∞ » ni le 01/01/1970 de `new Date(null)`.
const MISSING = "—";

/** Date + heure « 30/09/2026 04:52:57 » ; l'entrée illisible est rendue telle quelle. */
export function formatDateTime(iso: string | number | Date | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return MISSING;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString(intlLocale(), { timeZone: getTimeZone() });
}

/** Nombre localisé (« 1 234 567,75 » en fr) ; au plus `maxDecimals` décimales (2 par défaut). */
export function formatNumber(
  n: number | null | undefined,
  maxDecimals = 2,
  minDecimals = 0,
): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return MISSING;
  return numberFormat({
    maximumFractionDigits: maxDecimals,
    minimumFractionDigits: minDecimals,
  }).format(n);
}

/** Taille en octets lisible (« 3 Ko » / « 3 KB ») : unité adaptée, séparateur décimal localisé. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return MISSING;
  const units =
    getLocale() === "en" ? ["B", "KB", "MB", "GB", "TB"] : ["o", "Ko", "Mo", "Go", "To"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${formatNumber(value, i === 0 ? 0 : 1)} ${units[i]}`;
}
