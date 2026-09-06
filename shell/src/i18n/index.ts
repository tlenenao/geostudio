// SPDX-License-Identifier: Apache-2.0
import { fr } from "./catalog.fr";

export type MessageKey = keyof typeof fr;

/**
 * Rend un message du catalogue, en interpolant les `{paramètres}` nommés.
 *
 * Une clé inconnue est une erreur de compilation, pas une erreur d'exécution :
 * `MessageKey` est dérivée du catalogue lui-même. Un paramètre manquant laisse
 * son gabarit visible — un « {title} » à l'écran se remarque, une chaîne vide
 * non.
 */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const template: string = fr[key];
  if (params === undefined) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

/**
 * Résout une clé de message dont la provenance n'est pas garantie par le
 * compilateur (ex. `labelKey` renvoyé par `GET /roles/catalog`) vers une
 * clé réelle du catalogue, avec repli explicite sur `fallback` plutôt qu'un
 * cast non sûr (`as MessageKey`) : une clé absente du catalogue rendait
 * silencieusement une case à cocher sans libellé ni aria-label (REV-064).
 */
export function resolveMessageKey(key: string, fallback: MessageKey): MessageKey {
  return Object.hasOwn(fr, key) ? (key as MessageKey) : fallback;
}
