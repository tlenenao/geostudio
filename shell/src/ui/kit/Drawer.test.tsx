// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Drawer } from "./Drawer";
import { expectTokenizedClasses } from "./testUtils";

test("rend le contenu à droite par défaut", () => {
  const { container } = render(
    <Drawer open onOpenChange={() => {}} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("right-0");
  expectTokenizedClasses(container);
});

test("side=left positionne le panneau à gauche", () => {
  render(
    <Drawer open onOpenChange={() => {}} title="Explorateur" side="left">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("left-0");
});

test("Échap appelle onOpenChange(false)", async () => {
  const onOpenChange = vi.fn();
  render(
    <Drawer open onOpenChange={onOpenChange} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  await userEvent.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
