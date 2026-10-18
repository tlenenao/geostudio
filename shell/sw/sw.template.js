// SPDX-License-Identifier: Apache-2.0
// L8 : service worker du shell (PWA). Modèle : `vite.serviceWorker.ts` y injecte l'identifiant de
// build et la liste de précache, puis l'émet en `dist/sw.js` — il n'est donc jamais dans le graphe
// de l'entrée (filet de taille intact).
//
// Règle d'or : liste BLANCHE. Seuls les chargements du shell lui-même sont interceptés ; tout le
// reste (cœur sous /api ou /v1, /mcp, /embed, /admin/*, requêtes avec `Authorization`, autres
// origines) passe tel quel au réseau. Aucune réponse d'API n'est jamais mise en cache ici : les
// saisies hors-ligne vivent dans IndexedDB (src/offline), pas dans ce cache.
//
// Mise à jour : jamais d'activation automatique (`skipWaiting` seulement sur demande de la page,
// message `SKIP_WAITING`) — un rechargement surprise perdrait un formulaire en cours de saisie.
const BUILD_ID = "__BUILD_ID__";
const PRECACHE_CRITICAL = __PRECACHE_CRITICAL__;
const PRECACHE_OPTIONAL = __PRECACHE_OPTIONAL__;
const SHELL_CACHE = "gs-shell-" + BUILD_ID;
// Chunks chargés à la demande (et fichiers de /assets/ non hachés) : par build, donc bornés.
const ASSET_CACHE = "gs-assets-" + BUILD_ID;
const NAV_TIMEOUT_MS = 4000;

/** Routes du shell servies hors-ligne par repli sur `/index.html` (appli SPA). */
function isShellNavigation(pathname) {
  return pathname === "/" || pathname.startsWith("/collect/") || pathname.startsWith("/apps/");
}

async function precache() {
  const cache = await self.caches.open(SHELL_CACHE);
  await cache.addAll(PRECACHE_CRITICAL);
  // Facultatifs (config runtime, manifeste, icône) : leur absence ne bloque pas l'installation.
  await Promise.all(PRECACHE_OPTIONAL.map((u) => cache.add(u).catch(() => undefined)));
}

async function networkFirst(request) {
  const cache = await self.caches.open(SHELL_CACHE);
  try {
    const res = await fetch(request);
    if (res.ok) await cache.put(request, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(request);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(request) {
  const hit = await self.caches.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) {
    const cache = await self.caches.open(ASSET_CACHE);
    await cache.put(request, res.clone());
  }
  return res;
}

async function navigate(request) {
  const fallback = async () => {
    const cache = await self.caches.open(SHELL_CACHE);
    return (await cache.match("/index.html")) || Response.error();
  };
  try {
    const res = await fetch(request, { signal: AbortSignal.timeout(NAV_TIMEOUT_MS) });
    // Serveur du shell derrière un proxy en panne : le shell en cache vaut mieux qu'une 50x.
    if (res.status >= 502 && res.status <= 504) return await fallback();
    return res;
  } catch {
    return await fallback();
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(precache());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await self.caches.keys()) {
        if (key.startsWith("gs-") && key !== SHELL_CACHE && key !== ASSET_CACHE) {
          await self.caches.delete(key);
        }
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.headers.has("authorization")) return;
  if (request.headers.has("range")) return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    if (isShellNavigation(url.pathname)) event.respondWith(navigate(request));
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (PRECACHE_OPTIONAL.includes(url.pathname)) event.respondWith(networkFirst(request));
});
