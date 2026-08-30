// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { expect, test, vi } from "vitest";
import { Toast } from "./Toast";
import { expectTokenizedClasses } from "./testUtils";

// Polyfill pour jsdom : Radix Toast requiert cette méthode DOM (capture pointeur)
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}

function renderWithProvider(ui: React.ReactElement) {
  return render(
    <ToastPrimitive.Provider>
      {ui}
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

test("affiche titre et description quand ouvert", () => {
  const { container } = renderWithProvider(
    <Toast
      open
      onOpenChange={() => {}}
      title="Enregistré"
      description="Les modifications sont sauvegardées."
    />,
  );
  expect(screen.getByText("Enregistré")).toBeInTheDocument();
  expect(screen.getByText("Les modifications sont sauvegardées.")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur l'action l'exécute", async () => {
  const onClick = vi.fn();
  renderWithProvider(
    <Toast open onOpenChange={() => {}} title="Supprimé" action={{ label: "Annuler", onClick }} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onClick).toHaveBeenCalledTimes(1);
});
