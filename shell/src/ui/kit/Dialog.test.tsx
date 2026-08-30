// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  const { container } = render(
    <Dialog open onOpenChange={onOpenChange} title="Titre">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  expectTokenizedClasses(container);
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
