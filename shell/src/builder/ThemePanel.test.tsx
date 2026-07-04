import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Theme } from "../api/types";
import { ThemePanel } from "./ThemePanel";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

test("prefills every control from theme defaults when the theme is empty", () => {
  render(<ThemePanel theme={{}} onChange={vi.fn()} />);
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
