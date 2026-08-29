// SPDX-License-Identifier: Apache-2.0
const HARDCODED_COLOR_CLASS =
  /\b(?:bg|text|border|ring|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|blue|green|yellow|amber|lime|emerald|indigo|violet|purple|fuchsia|pink|rose|sky|cyan|orange|teal)-\d{2,3}\b/;

/**
 * Toute classe Tailwind de palette codée en dur (au lieu d'un token --gs-*)
 * casse l'ambiance sombre : cette assertion sert de proxy "testé dans les
 * deux ambiances" (jsdom ne peut pas rasteriser un rendu réel).
 */
export function expectTokenizedClasses(container: HTMLElement): void {
  if (HARDCODED_COLOR_CLASS.test(container.innerHTML)) {
    throw new Error(
      "classe Tailwind de palette codée en dur détectée — utiliser un token --gs-* (bg-surface, text-ink, border-rule, bg-accent, …) à la place",
    );
  }
}
