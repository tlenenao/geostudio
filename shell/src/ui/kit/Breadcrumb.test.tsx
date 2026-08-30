// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Breadcrumb } from "./Breadcrumb";
import { expectTokenizedClasses } from "./testUtils";

test("rend une navigation avec le fil d'Ariane, dernier élément non lien", () => {
  const { container } = render(
    <Breadcrumb items={[{ label: "Catalogue", href: "/" }, { label: "Carte topo" }]} />,
  );
  expect(screen.getByRole("navigation", { name: /Fil d'Ariane/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Catalogue" })).toHaveAttribute("href", "/");
  expect(screen.queryByRole("link", { name: "Carte topo" })).not.toBeInTheDocument();
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
