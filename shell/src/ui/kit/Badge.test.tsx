// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Badge } from "./Badge";
import { expectTokenizedClasses } from "./testUtils";

test("variant danger applique bg-danger-soft", () => {
  const { container } = render(<Badge variant="danger">Erreur</Badge>);
  expect(screen.getByText("Erreur")).toHaveClass("bg-danger-soft");
  expectTokenizedClasses(container);
});

test("variant par défaut applique bg-sunken", () => {
  render(<Badge>Brouillon</Badge>);
  expect(screen.getByText("Brouillon")).toHaveClass("bg-sunken");
});
