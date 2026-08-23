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
  expect(stops).toEqual(["#000000", "#808080", "#ffffff"]);
});

test("colorsForClasses on a sequential palette with n=1 returns the low color", () => {
  const palette = { kind: "sequential" as const, low: "#112233", high: "#445566" };
  expect(colorsForClasses(palette, 1)).toEqual(["#112233"]);
});
