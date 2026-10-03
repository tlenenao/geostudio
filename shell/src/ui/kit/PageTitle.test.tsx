// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { PageTitle } from "./PageTitle";

test("rend un h1 de taille et graisse uniformes", () => {
  render(<PageTitle>Titre</PageTitle>);
  const h = screen.getByRole("heading", { level: 1, name: "Titre" });
  expect(h).toHaveClass("text-lg", "font-semibold");
});
