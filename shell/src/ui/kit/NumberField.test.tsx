// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { NumberField } from "./NumberField";
import { expectTokenizedClasses } from "./testUtils";

test("le bouton + incrémente d'un pas", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <NumberField aria-label="Zoom" value={5} step={1} onValueChange={onValueChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Augmenter" }));
  expect(onValueChange).toHaveBeenCalledWith(6);
  expectTokenizedClasses(container);
});

test("le bouton - décrémente d'un pas et respecte min", async () => {
  const onValueChange = vi.fn();
  render(
    <NumberField aria-label="Zoom" value={0} min={0} step={1} onValueChange={onValueChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Diminuer" }));
  expect(onValueChange).not.toHaveBeenCalled();
});

test("la saisie directe d'un nombre valide notifie onValueChange", async () => {
  const onValueChange = vi.fn();
  render(<NumberField aria-label="Zoom" value={5} onValueChange={onValueChange} />);
  const input = screen.getByRole("spinbutton", { name: "Zoom" });
  await userEvent.clear(input);
  await userEvent.type(input, "12");
  expect(onValueChange).toHaveBeenLastCalledWith(12);
});
