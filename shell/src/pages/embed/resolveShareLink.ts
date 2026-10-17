// SPDX-License-Identifier: Apache-2.0
import { fetchWithTimeout } from "../../api/base";

export type ResolvedShareLink = {
  itemId: string;
  title: string;
  resourceType: string;
  expiresAt: string;
};

// GET /share-links/{token} est une route PUBLIQUE (core/app/items/
// routes.py::resolve_share_link_route, SP-54, inchangée par GAP-19) : pas
// d'ItemClient/Authorization ici, un simple fetch nu suffit — c'est
// exactement ce que la page d'embed doit rester capable de faire sans
// dépendre d'aucun état d'authentification de l'onglet hôte.
export async function resolveShareLink(coreUrl: string, token: string): Promise<ResolvedShareLink> {
  // fetchWithTimeout : un échec réseau (CORS, cœur arrêté) devient
  // CoreUnreachableError, distinct d'un 401 de lien expiré (AUD-135).
  const res = await fetchWithTimeout(`${coreUrl}/v1/share-links/${encodeURIComponent(token)}`);
  if (!res.ok) {
    throw new Error(`share link resolution failed: ${res.status}`);
  }
  return (await res.json()) as ResolvedShareLink;
}
