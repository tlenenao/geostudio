// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Theme } from "../api/types";
import { ThemePanel } from "./ThemePanel";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

test("prefills every control from theme defaults when the theme is empty", () => {
  const { container } = render(<ThemePanel theme={{}} onChange={vi.fn()} />);
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
  expect(screen.getByLabelText("Couleur primaire")).toHaveValue(DEFAULT_THEME_COLORS.primary);
  expect(screen.getByLabelText("Couleur de fond")).toHaveValue(DEFAULT_THEME_COLORS.background);
  expect(screen.getByLabelText("Couleur de surface")).toHaveValue(DEFAULT_THEME_COLORS.surface);
  expect(screen.getByLabelText("Couleur du texte")).toHaveValue(DEFAULT_THEME_COLORS.text);
  expect(screen.getByLabelText("Couleur atténuée")).toHaveValue(DEFAULT_THEME_COLORS.muted);
  expect(screen.getByLabelText("Couleur de bordure")).toHaveValue(DEFAULT_THEME_COLORS.border);
  expect(screen.getByLabelText("Police")).toHaveValue(DEFAULT_FONT);
  expect(screen.getByLabelText("Arrondi")).toHaveValue(DEFAULT_RADIUS);
  expect(screen.getByLabelText("Espacement")).toHaveValue(DEFAULT_SPACE);
});

test("changing the primary color emits an updated theme, other fields untouched", async () => {
  const onChange = vi.fn();
  const theme: Theme = { colors: { primary: "#2563eb" }, radius: "1rem" };
  render(<ThemePanel theme={theme} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Couleur primaire"));
  // jsdom's <input type="color"> doesn't support user-event typing directly;
  // fire the change event with fireEvent instead.
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(screen.getByLabelText("Couleur primaire"), { target: { value: "#ff0000" } });
  expect(onChange).toHaveBeenCalledWith({ colors: { primary: "#ff0000" }, radius: "1rem" });
});

test("changing the radius select emits an updated theme", async () => {
  const onChange = vi.fn();
  render(<ThemePanel theme={{}} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Arrondi"), "1rem");
  expect(onChange).toHaveBeenCalledWith({ radius: "1rem" });
});

test("REV-284(e) : signale une couleur atténuée illisible sur le fond", () => {
  render(<ThemePanel theme={{ colors: { muted: "#ffffff" } }} onChange={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Contraste insuffisant : « Couleur atténuée » sur la couleur de fond (1:1, minimum recommandé 4,5:1).",
  );
});

test("REV-284(e) : aucun avertissement avec le thème par défaut", () => {
  render(<ThemePanel theme={{}} onChange={vi.fn()} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
