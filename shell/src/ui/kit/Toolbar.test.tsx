// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Toolbar } from "./Toolbar";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur un bouton du toolbar déclenche son action", async () => {
  const onClick = vi.fn();
  const { container } = render(
    <Toolbar.Root aria-label="Actions carte">
      <Toolbar.Button onClick={onClick}>Mesurer</Toolbar.Button>
      <Toolbar.Separator />
      <Toolbar.Button onClick={() => {}}>Croquis</Toolbar.Button>
    </Toolbar.Root>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("flèche droite déplace le focus au bouton suivant (tabindex roulant)", async () => {
  render(
    <Toolbar.Root aria-label="Actions carte">
      <Toolbar.Button onClick={() => {}}>Mesurer</Toolbar.Button>
      <Toolbar.Button onClick={() => {}}>Croquis</Toolbar.Button>
    </Toolbar.Root>,
  );
  screen.getByRole("button", { name: "Mesurer" }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("button", { name: "Croquis" })).toHaveFocus();
});
