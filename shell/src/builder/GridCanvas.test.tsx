// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { WidgetItem } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { posFor } from "./grid";

const items: WidgetItem[] = [
  { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {} },
  { id: "b", widget: "image", x: 4, y: 0, w: 4, h: 2, props: {} },
];

function renderCanvas(over: Partial<React.ComponentProps<typeof GridCanvas>> = {}) {
  return render(
    <GridCanvas
      items={items}
      breakpoint="lg"
      editable
      selectedId={null}
      onSelect={over.onSelect ?? vi.fn()}
      onMoveItem={over.onMoveItem ?? vi.fn()}
      renderItem={(item) => <div>widget-{item.id}</div>}
      {...over}
    />,
  );
}

test("renders each item via renderItem", () => {
  renderCanvas();
  expect(screen.getByText("widget-a")).toBeInTheDocument();
  expect(screen.getByText("widget-b")).toBeInTheDocument();
});

test("selecting an item calls onSelect with its id", async () => {
  const onSelect = vi.fn();
  renderCanvas({ onSelect });
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  expect(onSelect).toHaveBeenCalledWith("a");
});

test("the move handle nudges the item by one cell", async () => {
  const onMoveItem = vi.fn();
  renderCanvas({ selectedId: "a", onMoveItem });
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a à droite" }));
  expect(onMoveItem).toHaveBeenCalledWith("a", 1, 0);
});

test("positions items at the active breakpoint and exposes data hooks", () => {
  const bpItems: WidgetItem[] = [
    {
      id: "a",
      widget: "text",
      x: 0,
      y: 0,
      w: 4,
      h: 2,
      props: {},
      layouts: { sm: { x: 5, y: 1, w: 6, h: 2 } },
    },
  ];
  const { container } = render(
    <GridCanvas
      items={bpItems}
      breakpoint="sm"
      editable={false}
      selectedId={null}
      onSelect={vi.fn()}
      onMoveItem={vi.fn()}
      renderItem={(item) => <div>widget-{item.id}</div>}
    />,
  );
  expect(container.querySelector("[data-breakpoint='sm']")).toBeInTheDocument();
  const wrapper = container.querySelector("[data-col]");
  expect(wrapper).toHaveAttribute("data-col", "5"); // sm override, not base 0
  expect(wrapper).toHaveAttribute("data-row", "1");
  // sanity: matches the pure helper
  expect(posFor(bpItems[0], "sm")).toEqual({ x: 5, y: 1, w: 6, h: 2 });
});

test("the canvas backdrop uses the surface theme token", () => {
  const { container } = renderCanvas();
  expect(container.firstChild).toHaveClass("bg-[var(--gs-color-surface)]");
});
