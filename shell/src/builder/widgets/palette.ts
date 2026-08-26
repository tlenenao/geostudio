// SPDX-License-Identifier: Apache-2.0
import type { ThemeColors } from "../../api/types";

export type PaletteId =
  "categorical-a" | "categorical-b" | "sequential-blue" | "sequential-warm" | "theme-primary";

export type ResolvedPalette =
  { kind: "categorical"; colors: string[] } | { kind: "sequential"; low: string; high: string };

// "categorical-a" is mapSymbology.ts's existing CATEGORICAL_PALETTE,
// unchanged — the default when an author picks no palette at all keeps
// rendering identically to pre-SP-25 maps.
export const CURATED_PALETTES: Record<Exclude<PaletteId, "theme-primary">, ResolvedPalette> = {
  "categorical-a": {
    kind: "categorical",
    colors: [
      "#2563eb",
      "#dc2626",
      "#16a34a",
      "#d97706",
      "#7c3aed",
      "#0891b2",
      "#db2777",
      "#65a30d",
    ],
  },
  "categorical-b": {
    kind: "categorical",
    colors: [
      "#0f766e",
      "#b45309",
      "#4338ca",
      "#be123c",
      "#3f6212",
      "#a21caf",
      "#0369a1",
      "#854d0e",
    ],
  },
  "sequential-blue": { kind: "sequential", low: "#dbeafe", high: "#1e3a8a" },
  "sequential-warm": { kind: "sequential", low: "#fef3c7", high: "#7c2d12" },
};

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  const c = (v: number) => Math.round(v).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}

function lerpColor(low: string, high: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(low);
  const [r2, g2, b2] = hexToRgb(high);
  return rgbToHex([r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t]);
}

// Rampe séquentielle dérivée de theme.colors.primary : du blanc jusqu'à la
// couleur primaire elle-même — pas de bibliothèque de teinte/luminosité,
// une interpolation RGB simple suffit pour un "clair → primary".
export function resolvePalette(
  id: PaletteId,
  themeColors: ThemeColors | undefined,
): ResolvedPalette | null {
  if (id === "theme-primary") {
    const primary = themeColors?.primary;
    if (!primary) return null;
    return { kind: "sequential", low: "#ffffff", high: primary };
  }
  return CURATED_PALETTES[id];
}

export function colorsForClasses(palette: ResolvedPalette, n: number): string[] {
  if (n <= 0) return [];
  if (palette.kind === "categorical") {
    return Array.from({ length: n }, (_, i) => palette.colors[i % palette.colors.length]);
  }
  if (n === 1) return [palette.low];
  return Array.from({ length: n }, (_, i) => lerpColor(palette.low, palette.high, i / (n - 1)));
}
