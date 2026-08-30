// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Chip } from "./Chip";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur le bouton de retrait appelle onRemove", async () => {
  const onRemove = vi.fn();
  const { container } = render(<Chip onRemove={onRemove}>type: map</Chip>);
  await userEvent.click(screen.getByRole("button", { name: "Retirer type: map" }));
  expect(onRemove).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("sans onRemove, aucun bouton de retrait n'est rendu", () => {
  render(<Chip>type: map</Chip>);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("children non-string : le bouton de retrait a un aria-label générique, pas '[object Object]'", async () => {
  const onRemove = vi.fn();
  render(
    <Chip onRemove={onRemove}>
      <strong>type: map</strong>
    </Chip>,
  );
  const button = screen.getByRole("button", { name: "Retirer" });
  await userEvent.click(button);
  expect(onRemove).toHaveBeenCalledTimes(1);
});
