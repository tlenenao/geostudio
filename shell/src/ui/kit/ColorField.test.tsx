// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ColorField } from "./ColorField";
import { expectTokenizedClasses } from "./testUtils";

test("la saisie du champ texte notifie onValueChange avec un hex valide", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={onValueChange} />,
  );
  const text = screen.getByRole("textbox", { name: "Couleur d'accent" });
  await userEvent.clear(text);
  await userEvent.type(text, "#336699");
  expect(onValueChange).toHaveBeenLastCalledWith("#336699");
  expectTokenizedClasses(container);
});

test("un hex incomplet ne notifie pas onValueChange", async () => {
  const onValueChange = vi.fn();
  render(
    <ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={onValueChange} />,
  );
  const text = screen.getByRole("textbox", { name: "Couleur d'accent" });
  await userEvent.clear(text);
  await userEvent.type(text, "#336");
  expect(onValueChange).not.toHaveBeenCalled();
});

test("le sélecteur natif porte la même valeur", () => {
  render(<ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={() => {}} />);
  const swatch = screen.getByLabelText("Couleur d'accent (sélecteur)");
  expect(swatch).toHaveValue("#0b6e77");
});
