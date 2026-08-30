// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Select } from "./Select";
import { expectTokenizedClasses } from "./testUtils";

// Polyfills pour jsdom : Radix Select requiert ces méthodes DOM
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const OPTIONS = [
  { value: "a", label: "Option A" },
  { value: "b", label: "Option B" },
];

test("affiche le libellé de la valeur sélectionnée", () => {
  const { baseElement } = render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toHaveTextContent("Option A");
  expectTokenizedClasses(baseElement);
});

test("ouvre au clic et sélectionne une option au clic", async () => {
  const onValueChange = vi.fn();
  const { baseElement } = render(
    <Select aria-label="Format" value="a" onValueChange={onValueChange} options={OPTIONS} />,
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Format" }));
  await screen.findByRole("option", { name: "Option B" });
  // Le panneau d'options est portalisé (document.body, hors de l'arbre RTL) —
  // vérifié tokenisé ici, pendant qu'il est ouvert, car le test précédent ne
  // l'ouvre jamais (trouvé en revue finale SP-29b : expectTokenizedClasses
  // sur le trigger fermé ne couvre jamais le Content portalisé).
  expectTokenizedClasses(baseElement);
  await userEvent.click(screen.getByRole("option", { name: "Option B" }));
  expect(onValueChange).toHaveBeenCalledWith("b");
});

test("disabled empêche l'ouverture", () => {
  render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} disabled />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toBeDisabled();
});
