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
  const template: string = messages[key];
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
  return n >= 0 && n < 2 ? one : many;
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
