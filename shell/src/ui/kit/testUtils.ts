// SPDX-License-Identifier: Apache-2.0
// REV-080 : le suffixe de nuance (`-\d{2,3}`) est rendu optionnel — bg-white/
// text-white/bg-black/text-black n'en portent jamais un (contrairement à
// bg-slate-900), et sont précisément les classes qui ont cassé l'ambiance
// sombre en SP-34 : le motif d'origine les laissait passer.
const HARDCODED_COLOR_CLASS =
  /\b(?:bg|text|border|ring|fill|stroke)-(?:white|black|slate|gray|zinc|neutral|stone|red|blue|green|yellow|amber|lime|emerald|indigo|violet|purple|fuchsia|pink|rose|sky|cyan|orange|teal)(?:-\d{2,3})?\b/;

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
