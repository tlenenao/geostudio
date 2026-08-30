// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Tabs } from "./Tabs";
import { expectTokenizedClasses } from "./testUtils";

const TABS = [
  { value: "info", label: "Informations", content: <p>Contenu info</p> },
  { value: "perms", label: "Permissions", content: <p>Contenu permissions</p> },
];

test("affiche le contenu de l'onglet par défaut", () => {
  const { container } = render(<Tabs defaultValue="info" tabs={TABS} />);
  expect(screen.getByText("Contenu info")).toBeInTheDocument();
  expect(screen.queryByText("Contenu permissions")).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur un onglet change le contenu affiché", async () => {
  render(<Tabs defaultValue="info" tabs={TABS} />);
  await userEvent.click(screen.getByRole("tab", { name: "Permissions" }));
  expect(screen.getByText("Contenu permissions")).toBeInTheDocument();
  expect(screen.queryByText("Contenu info")).not.toBeInTheDocument();
});

test("flèche droite déplace le focus vers l'onglet suivant", async () => {
  render(<Tabs defaultValue="info" tabs={TABS} />);
  screen.getByRole("tab", { name: "Informations" }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Permissions" })).toHaveFocus();
});
