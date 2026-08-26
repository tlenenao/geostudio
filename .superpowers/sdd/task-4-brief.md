## Task 4: Shell — `palette.ts`

**Files:**
- Create: `shell/src/builder/widgets/palette.ts`
- Test: `shell/src/builder/widgets/palette.test.ts`

**Interfaces:**
- Consumes: `ThemeColors` from `shell/src/api/types.ts` (already has
  `primary?: string` etc.).
- Produces: `PaletteId`, `ResolvedPalette`, `CURATED_PALETTES`,
  `resolvePalette(id, themeColors)`, `colorsForClasses(palette, n)` — all
  consumed by `mapSymbology.ts` in Task 6.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/palette.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { CURATED_PALETTES, colorsForClasses, resolvePalette } from "./palette";

test("resolvePalette returns a curated palette by id, ignoring theme", () => {
  const resolved = resolvePalette("categorical-a", undefined);
  expect(resolved).toEqual(CURATED_PALETTES["categorical-a"]);
});

test("resolvePalette returns null for theme-primary without a theme", () => {
  expect(resolvePalette("theme-primary", undefined)).toBeNull();
  expect(resolvePalette("theme-primary", {})).toBeNull();
});

test("resolvePalette derives a sequential ramp from theme.primary", () => {
  const resolved = resolvePalette("theme-primary", { primary: "#2563eb" });
  expect(resolved).toEqual({ kind: "sequential", low: expect.any(String), high: "#2563eb" });
});

test("colorsForClasses on a categorical palette slices then repeats", () => {
  const palette = CURATED_PALETTES["categorical-a"];
  const three = colorsForClasses(palette, 3);
  expect(three).toEqual(palette.kind === "categorical" ? palette.colors.slice(0, 3) : []);
  const many = colorsForClasses(palette, (palette as { colors: string[] }).colors.length + 2);
  expect(many[many.length - 1]).toBe((palette as { colors: string[] }).colors[1]); // wraps
});

test("colorsForClasses on a sequential palette interpolates n evenly-spaced RGB stops", () => {
  const palette = { kind: "sequential" as const, low: "#000000", high: "#ffffff" };
  const stops = colorsForClasses(palette, 3);
  expect(stops).toEqual(["#000000", "#7f7f7f", "#ffffff"]);
});

test("colorsForClasses on a sequential palette with n=1 returns the low color", () => {
  const palette = { kind: "sequential" as const, low: "#112233", high: "#445566" };
  expect(colorsForClasses(palette, 1)).toEqual(["#112233"]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/palette.test.ts`
Expected: FAIL — module `./palette` does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/builder/widgets/palette.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { ThemeColors } from "../../api/types";

export type PaletteId =
  | "categorical-a"
  | "categorical-b"
  | "sequential-blue"
  | "sequential-warm"
  | "theme-primary";

export type ResolvedPalette =
  | { kind: "categorical"; colors: string[] }
  | { kind: "sequential"; low: string; high: string };

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
export function resolvePalette(id: PaletteId, themeColors: ThemeColors | undefined): ResolvedPalette | null {
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/palette.test.ts`
Expected: PASS (6 tests). If the `theme-primary` test's exact `low` color
assertion needs adjusting to match `"#ffffff"` literally, fix the test, not
the implementation, once you've confirmed the implementation's choice is
deliberate (white low-anchor is the simplest correct choice, per this step).

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: all green, test count ≥ 1387 + 6.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/palette.ts shell/src/builder/widgets/palette.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le module de palettes de symbologie

Palettes curatées + rampe dérivée du thème, aucune bibliothèque de
couleur ajoutée (lerp RGB maison).
EOF
)"
```

---

