// SPDX-License-Identifier: Apache-2.0
import { fr } from "./catalog.fr";
// Imports de TYPES uniquement (effacés au build) : `MessageKey` couvre le noyau
// et tous les domaines sans que leur contenu entre dans le chemin de démarrage.
import type { admin } from "./domains/admin";
import type { automation } from "./domains/automation";
import type { map } from "./domains/map";
import type { misc } from "./domains/misc";
import type { widgets } from "./domains/widgets";

export type MessageKey =
  | keyof typeof fr
  | keyof typeof admin
  | keyof typeof automation
  | keyof typeof map
  | keyof typeof misc
  | keyof typeof widgets;

// Noyau (chemin de démarrage) + domaines enregistrés par leurs consommateurs
// (REV-307 b : le catalogue n'est plus tout entier dans le chunk d'entrée).
const messages: Record<string, string> = { ...fr };

// AUD-019 / D8 : locale active. Le français (catalogue source) est le repli ; l'anglais
// est un chunk chargé à la demande (jamais dans la charge initiale du français).
export type Locale = "fr" | "en";
export const LOCALES: readonly Locale[] = ["fr", "en"];
const STORAGE_KEY = "gs.locale";
let locale: Locale = "fr";
let en: Record<string, string> = {};

export function getLocale(): Locale {
  return locale;
}

/** Préférence stockée, sinon langue du navigateur (fr/en), sinon français. */
export function detectLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "fr" || stored === "en") return stored;
  } catch {
    /* stockage indisponible : repli navigateur */
  }
  const nav = typeof navigator === "undefined" ? "" : navigator.language.toLowerCase();
  return nav.startsWith("en") ? "en" : "fr";
}

/** Active une locale : charge le chunk anglais si besoin, pose `lang`/`dir` sur <html>. */
export async function activateLocale(next: Locale): Promise<void> {
  if (next === "en" && Object.keys(en).length === 0) {
    en = (await import("./en/all")).enMessages;
  }
  locale = next;
  if (typeof document !== "undefined") {
    document.documentElement.lang = next;
    document.documentElement.dir = "ltr"; // aucune locale RTL livrée (AUD-115 : RTL reporté)
  }
}

export function hasLocalePreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}

/** Mémorise la préférence puis recharge : `t()` n'est pas réactif (appelé au rendu). */
export function setLocalePreference(next: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* préférence non persistée : rechargement quand même */
  }
  window.location.reload();
}

/** Appelé par chaque fichier `domains/*.ts` à son évaluation. */
export function registerMessages(domain: Record<string, string>): void {
  Object.assign(messages, domain);
}

/**
 * Rend un message du catalogue, en interpolant les `{paramètres}` nommés.
 *
 * Une clé inconnue est une erreur de compilation, pas une erreur d'exécution :
 * `MessageKey` est dérivée du catalogue lui-même. Un paramètre manquant laisse
 * son gabarit visible — un « {title} » à l'écran se remarque, une chaîne vide
 * non. Un domaine non enregistré (consommateur sans l'import de son domaine,
 * interdit par `domains.test.ts`) se comporte comme une clé inconnue.
 */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const template: string = (locale === "en" ? en[key] : undefined) ?? messages[key];
  if (params === undefined) return template;
  // Clé inconnue (domaine non enregistré) : clé brute plutôt qu'une TypeError.
  // Sans params, `undefined` est conservé (cf. index.test.ts).
  if (template === undefined) return key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

/**
 * Sélectionne la clé de message accordée en nombre (français : singulier
 * pour 0 et 1, pluriel à partir de 2 — « 0 élément », contrairement à l'anglais).
 */
export function plural(n: number, one: MessageKey, many: MessageKey): MessageKey {
  // Règle fr historique conservée (0 et 1,5 au singulier) ; `Intl.PluralRules` ailleurs.
  if (locale === "fr") return n >= 0 && n < 2 ? one : many;
  return new Intl.PluralRules(locale).select(n) === "one" ? one : many;
}

/**
 * Résout une clé de message dont la provenance n'est pas garantie par le
 * compilateur (ex. `labelKey` renvoyé par `GET /roles/catalog`) vers une
 * clé réelle du catalogue, avec repli explicite sur `fallback` plutôt qu'un
 * cast non sûr (`as MessageKey`) : une clé absente du catalogue rendait
 * silencieusement une case à cocher sans libellé ni aria-label (REV-064).
 */
export function resolveMessageKey(key: string, fallback: MessageKey): MessageKey {
  return Object.hasOwn(messages, key) ? (key as MessageKey) : fallback;
}

// Boot : la locale doit être active AVANT l'évaluation des modules qui appellent `t()` au
// niveau module (tables de libellés) — d'où l'attente au niveau module. Les tests restent en fr
// (jsdom annonce `en-US`) et pilotent `activateLocale` eux-mêmes.
if (import.meta.env.MODE !== "test" && detectLocale() === "en") await activateLocale("en");
