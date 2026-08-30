// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Button } from "./Button";
import { expectTokenizedClasses } from "./testUtils";

test("rend un bouton cliquable", async () => {
  const onClick = vi.fn();
  const { container } = render(<Button onClick={onClick}>Valider</Button>);
  await userEvent.click(screen.getByRole("button", { name: "Valider" }));
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("respecte disabled", async () => {
  const onClick = vi.fn();
  render(
    <Button disabled onClick={onClick}>
      Valider
    </Button>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Valider" }));
  expect(onClick).not.toHaveBeenCalled();
});

test("variant danger applique la classe bg-danger", () => {
  render(<Button variant="danger">Supprimer</Button>);
  expect(screen.getByRole("button", { name: "Supprimer" })).toHaveClass("bg-danger");
});

test("size icon est carrée", () => {
  render(<Button size="icon">×</Button>);
  expect(screen.getByRole("button")).toHaveClass("w-9", "h-9");
});
