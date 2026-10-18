// SPDX-License-Identifier: Apache-2.0
const cache = new Map<string, Promise<unknown>>();

// AUD-109 : avec un SRI, le module est chargé par `<script type="module" integrity>` — le
// navigateur refuse d'exécuter un contenu dont le condensat diffère (et la CSP
// `script-src 'self' <origine>` reste valable, contrairement à un import de Blob URL).
function loadWithIntegrity(url: string, integrity: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.type = "module";
    script.src = url;
    script.integrity = integrity;
    script.crossOrigin = "anonymous";
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      reject(new Error(`extension module failed to load or failed its integrity check: ${url}`));
    };
    document.head.appendChild(script);
  });
}

function defaultImport(url: string, integrity?: string | null): Promise<unknown> {
  if (integrity) return loadWithIntegrity(url, integrity);
  return import(/* @vite-ignore */ url);
}

export function ensureModuleLoaded(
  url: string,
  importFn: (url: string, integrity?: string | null) => Promise<unknown> = defaultImport,
  integrity?: string | null,
): Promise<unknown> {
  // Le SRI fait partie de la clé : un manifeste ré-épinglé recharge le module (AUD-109 #9).
  const key = `${url}|${integrity ?? ""}`;
  let p = cache.get(key);
  if (!p) {
    p = importFn(url, integrity);
    cache.set(key, p);
    // Une panne transitoire ne doit pas figer le widget jusqu'au prochain F5 (d24 #7).
    p.catch(() => {
      if (cache.get(key) === p) cache.delete(key);
    });
  }
  return p;
}

/** Résout quand le custom element est défini ; rejette après `timeoutMs` (module chargé
 *  mais sans `customElements.define(tag, …)` : message lisible plutôt qu'un élément inerte). */
export function whenElementDefined(tag: string, timeoutMs = 3000): Promise<void> {
  if (customElements.get(tag)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`custom element <${tag}> was not defined by the module`)),
      timeoutMs,
    );
    void customElements.whenDefined(tag).then(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}

export function _resetModuleCache(): void {
  cache.clear();
}
