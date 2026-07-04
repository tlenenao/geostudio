import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("filter widget emits changed with the configured field", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m", from: "flt1", event: "changed", to: "list1", action: "setFilter" }]);
  const Filter = getWidget("filter")!.Component;
  render(<Filter props={{ field: "nom", label: "Filtrer" }} ctx={{ mode: "runtime", bus, widgetId: "flt1" } as WidgetContext} />);
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "A");
  expect(handler).toHaveBeenLastCalledWith({ nom: "A" });
});

test("filter widget declares a changed event and edits its field", async () => {
  expect(getWidget("filter")!.events).toContain("changed");
  const onChange = vi.fn();
  const Panel = getWidget("filter")!.PropsPanel;
  render(<Panel props={{ field: "" }} dataSources={[]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Champ à filtrer"), "nom");
  const last = onChange.mock.calls.at(-1)![0];
  expect(String(last.field).endsWith("m")).toBe(true);
});

test("filter label and input use the theme text/border tokens", () => {
  const Filter = getWidget("filter")!.Component;
  render(<Filter props={{ label: "Rechercher" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Rechercher")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByLabelText("Valeur du filtre")).toHaveClass("border-[var(--gs-color-border)]");
});
