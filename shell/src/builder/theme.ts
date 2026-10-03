// SPDX-License-Identifier: Apache-2.0
import type { CSSProperties } from "react";
import type { Theme, ThemeColors } from "../api/types";

export const DEFAULT_THEME_COLORS: Required<ThemeColors> = {
  primary: "#2563eb",
  background: "#ffffff",
  surface: "#f8fafc",
  text: "#0f172a",
  muted: "#64748b",
  border: "#e2e8f0",
};
// i18n-ok: pile de polices CSS (« sans-serif »), pas du français
export const DEFAULT_FONT = "system-ui, sans-serif";
export const DEFAULT_RADIUS = "0.375rem";
export const DEFAULT_SPACE = "0.5rem";

// Maps a sparse Theme onto the fixed set of --gs-* custom properties the
// renderer applies on its root container, filling any absent field with its
// documented default so widgets can always resolve every variable.
export function themeToCssVars(theme: Theme): CSSProperties {
  const colors = { ...DEFAULT_THEME_COLORS, ...theme.colors };
  return {
    "--gs-color-primary": colors.primary,
    "--gs-color-background": colors.background,
    "--gs-color-surface": colors.surface,
    "--gs-color-text": colors.text,
    "--gs-color-muted": colors.muted,
    "--gs-color-border": colors.border,
    "--gs-font": theme.font ?? DEFAULT_FONT,
    "--gs-radius": theme.radius ?? DEFAULT_RADIUS,
    "--gs-space": theme.space ?? DEFAULT_SPACE,
  } as CSSProperties;
}

// P33.02 : la toile d'une app porte son propre thème (clair par défaut) ; les
// classes sémantiques du shell (text-ink-2, bg-surface…) qui s'y trouvent
// doivent le suivre, sinon un shell en thème sombre y dépose du texte clair
// sur fond clair. On rebranche donc les jetons du shell sur ceux de l'app.
export function themeToShellTokens(theme: Theme): CSSProperties {
  const colors = { ...DEFAULT_THEME_COLORS, ...theme.colors };
  return {
    "--gs-background": colors.background,
    "--gs-surface": colors.surface,
    "--gs-raised": colors.background,
    "--gs-ink": colors.text,
    "--gs-ink-2": colors.muted,
    "--gs-ink-3": colors.muted,
    "--gs-muted": colors.muted,
    "--gs-rule": colors.border,
    "--gs-rule-2": colors.border,
    "--gs-control": colors.muted,
    color: colors.text,
  } as CSSProperties;
}
