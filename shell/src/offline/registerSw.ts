// SPDX-License-Identifier: Apache-2.0
// L8 : enregistrement du service worker (build de production seulement) et détection d'une
// nouvelle version. Jamais d'activation automatique : la page propose, l'utilisateur décide
// (un rechargement surprise perdrait une saisie en cours).

/** `onUpdateReady(apply)` : une nouvelle version est installée ; `apply()` l'active et recharge. */
export function registerServiceWorker(onUpdateReady: (apply: () => void) => void): void {
  if (!import.meta.env.PROD || typeof navigator === "undefined" || !navigator.serviceWorker) return;
  const sw = navigator.serviceWorker;
  const announce = (waiting: ServiceWorker) =>
    onUpdateReady(() => {
      sw.addEventListener("controllerchange", () => window.location.reload(), { once: true });
      waiting.postMessage({ type: "SKIP_WAITING" });
    });
  const start = () => {
    sw.register("/sw.js")
      .then((reg) => {
        // Seule une MISE À JOUR (un contrôleur existe déjà) est annoncée, pas la 1re installation.
        if (reg.waiting && sw.controller) announce(reg.waiting);
        reg.addEventListener("updatefound", () => {
          const installing = reg.installing;
          installing?.addEventListener("statechange", () => {
            if (installing.state === "installed" && sw.controller) announce(installing);
          });
        });
      })
      .catch(() => {
        // SW refusé (contexte non sécurisé, navigation privée…) : le shell marche sans.
      });
  };
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
}
