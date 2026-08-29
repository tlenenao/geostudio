// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Input } from "./Input";
import { expectTokenizedClasses } from "./testUtils";

test("saisie contrôlée", async () => {
  const { container } = render(<Input aria-label="Titre" defaultValue="" />);
  const input = screen.getByRole("textbox", { name: "Titre" });
  await userEvent.type(input, "abc");
  expect(input).toHaveValue("abc");
  expectTokenizedClasses(container);
});

test("disabled empêche la saisie", async () => {
  render(<Input aria-label="Titre" disabled defaultValue="" />);
  const input = screen.getByRole("textbox", { name: "Titre" });
  expect(input).toBeDisabled();
});
