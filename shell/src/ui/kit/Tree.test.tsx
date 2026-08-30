// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Tree, type TreeNode } from "./Tree";
import { expectTokenizedClasses } from "./testUtils";

const NODES: TreeNode[] = [
  {
    id: "carte",
    label: "Cartes",
    children: [{ id: "carte-1", label: "Carte topo" }],
  },
  { id: "app", label: "Apps" },
];

test("les enfants sont repliés par défaut", () => {
  const { container } = render(<Tree nodes={NODES} />);
  expect(screen.queryByText("Carte topo")).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur un nœud parent déplie ses enfants", async () => {
  render(<Tree nodes={NODES} />);
  await userEvent.click(screen.getByRole("button", { name: "Cartes" }));
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
});

test("clic sur une feuille appelle onSelect avec son id", async () => {
  const onSelect = vi.fn();
  render(<Tree nodes={NODES} onSelect={onSelect} />);
  await userEvent.click(screen.getByText("Apps"));
  expect(onSelect).toHaveBeenCalledWith("app");
});
