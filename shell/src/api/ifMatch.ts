// SPDX-License-Identifier: Apache-2.0
// P09.04/REV-271 : `If-Match: "<version lue>"` fait refuser (412) par le cœur
// une écriture de config issue d'une version périmée. `undefined` = client
// qui ne connaît pas de version (historique) : pas d'en-tête, dernier
// écrivain gagne. À passer en `extraHeaders` de `base.request`.
export function ifMatchHeader(baseVersion: number | undefined): Record<string, string> | undefined {
  return baseVersion === undefined ? undefined : { "If-Match": `"${baseVersion}"` };
}
