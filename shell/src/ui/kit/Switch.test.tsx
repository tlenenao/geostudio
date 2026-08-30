// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Switch } from "./Switch";
import { expectTokenizedClasses } from "./testUtils";

test("clic bascule l'état", async () => {
  const onCheckedChange = vi.fn();
  const { container } = render(
    <Switch aria-label="Activer" checked={false} onCheckedChange={onCheckedChange} />,
  );
  const toggle = screen.getByRole("switch", { name: "Activer" });
  expect(toggle).toHaveAttribute("aria-checked", "false");
  await userEvent.click(toggle);
  expect(onCheckedChange).toHaveBeenCalledWith(true);
  expectTokenizedClasses(container);
});

test("barre espace bascule au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(<Switch aria-label="Activer" checked={false} onCheckedChange={onCheckedChange} />);
  screen.getByRole("switch", { name: "Activer" }).focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).toHaveBeenCalledWith(true);
});

test("disabled empêche le changement", async () => {
  const onCheckedChange = vi.fn();
  render(
    <Switch aria-label="Activer" checked={false} disabled onCheckedChange={onCheckedChange} />,
  );
  expect(screen.getByRole("switch", { name: "Activer" })).toBeDisabled();
});

test("disabled empêche le changement au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(
    <Switch aria-label="Activer" checked={false} disabled onCheckedChange={onCheckedChange} />,
  );
  screen.getByRole("switch", { name: "Activer" }).focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).not.toHaveBeenCalled();
});
