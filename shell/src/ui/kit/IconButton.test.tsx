// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { X } from "lucide-react";
import { expect, test, vi } from "vitest";
import { IconButton } from "./IconButton";
import { expectTokenizedClasses } from "./testUtils";

test("expose un accessible name via aria-label, pas de texte visible", async () => {
  const onClick = vi.fn();
  const { container } = render(<IconButton icon={<X />} aria-label="Fermer" onClick={onClick} />);
  const button = screen.getByRole("button", { name: "Fermer" });
  await userEvent.click(button);
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});
