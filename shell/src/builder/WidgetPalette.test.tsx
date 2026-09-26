// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { WidgetPalette } from "./WidgetPalette";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("lists widgets and emits the type on click", async () => {
  const onAdd = vi.fn();
  const { container } = render(<WidgetPalette onAdd={onAdd} />);
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  expect(onAdd).toHaveBeenCalledWith("text");
});

test("excludes the given widget types from the list", () => {
  const onAdd = vi.fn();
  render(<WidgetPalette onAdd={onAdd} exclude={["image", "button"]} />);
  expect(screen.getByRole("button", { name: "Texte" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Image" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Bouton" })).not.toBeInTheDocument();
});
