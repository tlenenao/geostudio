import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { WidgetItem } from "../api/types";
import { GridCanvas } from "./GridCanvas";

const items: WidgetItem[] = [
  { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {} },
  { id: "b", widget: "image", x: 4, y: 0, w: 4, h: 2, props: {} },
];

function renderCanvas(over: Partial<React.ComponentProps<typeof GridCanvas>> = {}) {
  return render(
    <GridCanvas
      items={items}
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
