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
