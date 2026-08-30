// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Spinner } from "./Spinner";
import { expectTokenizedClasses } from "./testUtils";

test("expose role=status avec un nom accessible", () => {
  const { container } = render(<Spinner aria-label="Chargement" />);
  expect(screen.getByRole("status", { name: "Chargement" })).toBeInTheDocument();
  expectTokenizedClasses(container);
});
