// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Checkbox } from "./Checkbox";
import { expectTokenizedClasses } from "./testUtils";

test("clic bascule l'état et appelle onCheckedChange", async () => {
  const onCheckedChange = vi.fn();
  const { container } = render(
    <Checkbox aria-label="Sélectionner" checked={false} onCheckedChange={onCheckedChange} />,
  );
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  expect(box).toHaveAttribute("aria-checked", "false");
  await userEvent.click(box);
  expect(onCheckedChange).toHaveBeenCalledWith(true);
  expectTokenizedClasses(container);
});

test("la barre espace bascule l'état au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(<Checkbox aria-label="Sélectionner" checked={false} onCheckedChange={onCheckedChange} />);
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  box.focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).toHaveBeenCalledWith(true);
});

test("checked=true affiche l'indicateur", () => {
  render(<Checkbox aria-label="Sélectionner" checked onCheckedChange={() => {}} />);
  expect(screen.getByRole("checkbox", { name: "Sélectionner" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

test("disabled empêche le changement", async () => {
  const onCheckedChange = vi.fn();
  render(
    <Checkbox
      aria-label="Sélectionner"
      checked={false}
      disabled
      onCheckedChange={onCheckedChange}
    />,
  );
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  expect(box).toBeDisabled();
  await userEvent.click(box);
  expect(onCheckedChange).not.toHaveBeenCalled();
});

test("disabled empêche le changement au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(
    <Checkbox
      aria-label="Sélectionner"
      checked={false}
      disabled
      onCheckedChange={onCheckedChange}
    />,
  );
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  box.focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).not.toHaveBeenCalled();
});
