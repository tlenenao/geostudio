// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Banner } from "./Banner";
import { expectTokenizedClasses } from "./testUtils";

test("variant danger porte role=alert", () => {
  const { container } = render(<Banner variant="danger">Échec de l'enregistrement.</Banner>);
  expect(screen.getByRole("alert")).toHaveTextContent("Échec de l'enregistrement.");
  expectTokenizedClasses(container);
});

test("variant info ne porte pas role=alert", () => {
  render(<Banner variant="info">Mode démonstration.</Banner>);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Mode démonstration.")).toBeInTheDocument();
});
