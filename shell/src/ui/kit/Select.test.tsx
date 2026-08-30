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
  const { container } = render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toHaveTextContent("Option A");
  expectTokenizedClasses(container);
});

test("ouvre au clic et sélectionne une option au clic", async () => {
  const onValueChange = vi.fn();
  render(<Select aria-label="Format" value="a" onValueChange={onValueChange} options={OPTIONS} />);
  await userEvent.click(screen.getByRole("combobox", { name: "Format" }));
  await userEvent.click(await screen.findByRole("option", { name: "Option B" }));
  expect(onValueChange).toHaveBeenCalledWith("b");
});

test("disabled empêche l'ouverture", () => {
  render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} disabled />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toBeDisabled();
});
