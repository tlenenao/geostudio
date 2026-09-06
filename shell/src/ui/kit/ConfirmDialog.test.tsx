// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur Annuler appelle onCancel", async () => {
  const onCancel = vi.fn();
  // REV-081 : `ConfirmDialog` rend son contenu dans un portail Radix (hors de
  // `container`, dans `document.body`) — `expectTokenizedClasses(container)`
  // inspectait un nœud vide. `baseElement` (document.body par défaut, sans
  // option `container` custom) couvre bien le contenu portalisé.
  const { baseElement } = render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Supprimer « Carte topo » ? Cette action est irréversible."
      confirmLabel="Supprimer"
      onConfirm={() => {}}
      onCancel={onCancel}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onCancel).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(baseElement);
});

test("clic sur le bouton de confirmation appelle onConfirm", async () => {
  const onConfirm = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Confirmer ?"
      confirmLabel="Supprimer"
      onConfirm={onConfirm}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
});

test("pending désactive le bouton de confirmation", () => {
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Confirmer ?"
      confirmLabel="Supprimer"
      onConfirm={() => {}}
      onCancel={() => {}}
      pending
    />,
  );
  expect(screen.getByRole("button", { name: "Supprimer" })).toBeDisabled();
});
