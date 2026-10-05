// SPDX-License-Identifier: Apache-2.0
// Réglage d'ambiance clair/sombre/auto (P33.20, WCAG 1.4.x : l'utilisateur doit
// pouvoir contrarier son OS). « auto » = pas d'attribut data-theme, c'est la
// media query `prefers-color-scheme` de tokens.css qui décide.
export type ThemePreference = "auto" | "light" | "dark";

/**
 * Valeur courante d'un jeton `--gs-*` (MapLibre/canvas ne savent pas lire
 * `var(--…)`) : à appeler au montage de la carte pour suivre le thème actif.
 * `fallback` sert hors navigateur réel (jsdom ne résout pas les variables).
 */
export function readToken(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/**
 * REV-285(e) : notifie un changement d'ambiance (réglage explicite via
 * `data-theme`, OU `prefers-color-scheme` en « auto »). Retourne le désabonnement.
 */
export function onThemeChange(cb: () => void): () => void {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const mql = window.matchMedia?.("(prefers-color-scheme: dark)"); // absent de jsdom
  mql?.addEventListener("change", cb);
  return () => {
    observer.disconnect();
    mql?.removeEventListener("change", cb);
  };
}

const STORAGE_KEY = "gs-theme";

export function readThemePreference(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto"; // stockage indisponible (navigation privée, politique)
  }
}

export function applyThemePreference(pref: ThemePreference): void {
  if (pref === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = pref;
}

export function saveThemePreference(pref: ThemePreference): void {
  try {
    if (pref === "auto") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, pref);
  } catch {
    /* le réglage reste appliqué pour la session */
  }
  applyThemePreference(pref);
}
