// SPDX-License-Identifier: Apache-2.0
// Extrait de MapView.tsx (revue finale Vague B, C2) pour être partagé avec
// LayersPanel.tsx sans que ce dernier importe MapView (maplibre-gl +
// deck.gl) : logique strictement inchangée, toujours une seule copie.
// Path segments distinguishing our own authenticated proxies (served by
// core, design docs §4) from an externally-hosted resource at the same-
// looking path — the latter must never receive our session's bearer token.
const HOSTED_TILESET3D_PATH = "/tileset3d/";
const HOSTED_TERRAIN3D_PATH = "/terrain3d/";
const HOSTED_COLLECTION_PATH = "/collections/";

// Real "is this hosted by us" check: a substring match on the URL is not
// enough — layer/terrain URLs are freeform (an author can type any external
// URL via LayerPicker/TerrainPanel), so an attacker-controlled URL like
// "https://attacker.example/x/terrain3d/y/tiles/0/0/0.png" would otherwise
// pass a bare `.includes(pathPrefix)` check and leak the session's bearer
// token cross-origin. A URL only counts as hosted when its origin matches
// the configured core API's origin AND its pathname starts with the proxy
// route's own path segment. Shared by both the tileset3d (deck.gl
// Tile3DLayer, see buildTiles3DLayer) and terrain3d (MapLibre
// transformRequest, see below) call sites — never duplicate this check.
// Le chemin de base du cœur fait partie de la comparaison depuis C1 de la
// revue finale SP-24 : en production `VITE_CORE_URL` vaut `https://hôte/api`
// (docker-compose.prod.yml), donc une vraie URL de tuile est
// `/api/collections/…` et ne commence PAS par `/collections/`. Le jeton
// n'était alors jamais attaché et toute collection non publique renvoyait un
// 404 — invisible en test, où toutes les URL de cœur étaient sans chemin.
function isHostedCoreUrl(url: string, coreUrl: string | undefined, pathPrefix: string): boolean {
  if (!coreUrl) return false;
  try {
    const target = new URL(url);
    const core = new URL(coreUrl);
    // "https://hôte" → pathname "/" → base "" ; "https://hôte/api/" → "/api".
    const base = core.pathname.replace(/\/+$/, "");
    return target.origin === core.origin && target.pathname.startsWith(base + pathPrefix);
  } catch {
    return false;
  }
}

export function isHostedTilesetUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TILESET3D_PATH);
}

export function isHostedTerrainUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TERRAIN3D_PATH);
}

// Les tuiles MVT d'une collection (SP-24) et le GeoJSON /items sont servis par
// le cœur sous can() : ils doivent porter le jeton de session, sinon une
// collection non publique n'est pas lisible du tout. Même vérification
// d'origine réelle que pour tileset3d/terrain3d — jamais un includes().
export function isHostedCollectionUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_COLLECTION_PATH);
}
