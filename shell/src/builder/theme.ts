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
