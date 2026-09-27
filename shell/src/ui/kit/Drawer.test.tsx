// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { Drawer } from "./Drawer";
import { expectTokenizedClasses } from "./testUtils";

test("rend le contenu à droite par défaut", () => {
  const { baseElement } = render(
    <Drawer open onOpenChange={() => {}} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("right-0");
  expectTokenizedClasses(baseElement);
});

test("le conteneur de contenu défile verticalement (REV-086)", () => {
  render(
    <Drawer open onOpenChange={() => {}} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("overflow-y-auto");
});

test("side=left positionne le panneau à gauche", () => {
  render(
    <Drawer open onOpenChange={() => {}} title="Explorateur" side="left">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("left-0");
});

test("transmet id à DialogPrimitive.Content pour un aria-controls externe (usePanelTrigger)", () => {
  render(
    <Drawer open onOpenChange={() => {}} title="Explorateur" id="panel-r-abc">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveAttribute("id", "panel-r-abc");
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

test("D48 : le focus revient sur le déclencheur externe après une fermeture au clavier (Échap) — filet de non-régression", async () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Ouvrir
        </button>
        <Drawer open={open} onOpenChange={setOpen} title="Explorateur">
          <p>Contenu</p>
        </Drawer>
      </>
    );
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Ouvrir" });
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(document.activeElement).toBe(trigger);
});
