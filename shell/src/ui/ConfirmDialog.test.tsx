import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

test("confirm and cancel fire their callbacks", async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Sûr ?"
      confirmLabel="Supprimer"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  expect(screen.getByText("Sûr ?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(onConfirm).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onCancel).toHaveBeenCalled();
});
