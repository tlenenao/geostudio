// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Textarea } from "./Textarea";
import { expectTokenizedClasses } from "./testUtils";

test("saisie multiligne contrôlée", async () => {
  const { container } = render(<Textarea aria-label="Description" defaultValue="" />);
  const textarea = screen.getByRole("textbox", { name: "Description" });
  await userEvent.type(textarea, "ligne 1{enter}ligne 2");
  expect(textarea).toHaveValue("ligne 1\nligne 2");
  expectTokenizedClasses(container);
});
