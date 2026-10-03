// SPDX-License-Identifier: Apache-2.0
import { loadRuntimeConfig } from "../config";

/** `thumbnailUrl` d'un item PUBLIÉ : chemin relatif à la racine du cœur
 * (`/public/items/{id}/thumbnail`, lisible sans jeton) — rendu absolu pour un
 * `<img>`, qui ne passe pas par `ItemClient` (P35.12). */
export function publicThumbnailSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^https?:\/\//.test(url)) return url;
  return `${loadRuntimeConfig().coreUrl}/v1${url}`;
}
