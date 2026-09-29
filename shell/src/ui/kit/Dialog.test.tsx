// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { Dialog } from "./Dialog";
import { expectTokenizedClasses } from "./testUtils";

test("ne rend rien quand fermé", () => {
  render(
    <Dialog open={false} onOpenChange={() => {}} title="T">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("rend le contenu et le titre quand ouvert, Échap ferme", async () => {
  const onOpenChange = vi.fn();
  const { baseElement } = render(
    <Dialog open onOpenChange={onOpenChange} title="Titre">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  expectTokenizedClasses(baseElement);
});

test("le focus est piégé dans la boîte de dialogue à l'ouverture", async () => {
  render(
    <Dialog open onOpenChange={() => {}} title="Titre">
      <button>Premier</button>
      <button>Second</button>
    </Dialog>,
  );
  expect(await screen.findByRole("button", { name: "Premier" })).toHaveFocus();
});

test("size='lg' rend une largeur plus grande que le défaut 'md'", () => {
  const { rerender } = render(
    <Dialog open onOpenChange={() => {}} title="T" size="lg">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-2xl");

  rerender(
    <Dialog open onOpenChange={() => {}} title="T">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-md");
});

// D48, revue finale Vague C (point 3) : même filet de non-régression que
// Drawer.test.tsx ("le focus revient sur le déclencheur externe après une
// fermeture au clavier (Échap)") — Dialog.tsx avait le même défaut, jamais
// corrigé jusqu'ici. Falsifié : retirer temporairement
// `useFocusRestoreOnClose`/`onCloseAutoFocus` de Dialog.tsx fait échouer ce
// test (le focus part sur `document.body` au lieu du déclencheur).
test("D48 : le focus revient sur le déclencheur externe après une fermeture au clavier (Échap)", async () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Ouvrir
        </button>
        <Dialog open={open} onOpenChange={setOpen} title="Titre">
          <p>corps</p>
        </Dialog>
      </>
    );
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Ouvrir" });
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(document.activeElement).toBe(trigger);
});
