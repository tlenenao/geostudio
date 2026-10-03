// SPDX-License-Identifier: Apache-2.0
// Réglage d'ambiance clair/sombre/auto (P33.20, WCAG 1.4.x : l'utilisateur doit
// pouvoir contrarier son OS). « auto » = pas d'attribut data-theme, c'est la
// media query `prefers-color-scheme` de tokens.css qui décide.
export type ThemePreference = "auto" | "light" | "dark";

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
