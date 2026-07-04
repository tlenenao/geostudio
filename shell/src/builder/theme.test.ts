import { expect, test } from "vitest";
import { themeToCssVars, DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

test("an empty theme resolves to all documented defaults", () => {
  const vars = themeToCssVars({});
  expect(vars).toMatchObject({
    "--gs-color-primary": DEFAULT_THEME_COLORS.primary,
    "--gs-color-background": DEFAULT_THEME_COLORS.background,
    "--gs-color-surface": DEFAULT_THEME_COLORS.surface,
    "--gs-color-text": DEFAULT_THEME_COLORS.text,
    "--gs-color-muted": DEFAULT_THEME_COLORS.muted,
    "--gs-color-border": DEFAULT_THEME_COLORS.border,
    "--gs-font": DEFAULT_FONT,
    "--gs-radius": DEFAULT_RADIUS,
    "--gs-space": DEFAULT_SPACE,
  });
});

test("a partial theme overrides only the fields it sets", () => {
  const vars = themeToCssVars({ colors: { primary: "#ff0000" }, radius: "1rem" });
  expect(vars).toMatchObject({
    "--gs-color-primary": "#ff0000",
    "--gs-color-background": DEFAULT_THEME_COLORS.background, // untouched
    "--gs-radius": "1rem",
    "--gs-space": DEFAULT_SPACE, // untouched
  });
});

test("a fully specified theme is passed through verbatim", () => {
  const theme = {
    colors: { primary: "#111111", background: "#222222", surface: "#333333", text: "#444444", muted: "#555555", border: "#666666" },
    font: "Georgia, serif",
    radius: "0px",
    space: "1rem",
  };
  expect(themeToCssVars(theme)).toEqual({
    "--gs-color-primary": "#111111",
    "--gs-color-background": "#222222",
    "--gs-color-surface": "#333333",
    "--gs-color-text": "#444444",
    "--gs-color-muted": "#555555",
    "--gs-color-border": "#666666",
    "--gs-font": "Georgia, serif",
    "--gs-radius": "0px",
    "--gs-space": "1rem",
  });
});
