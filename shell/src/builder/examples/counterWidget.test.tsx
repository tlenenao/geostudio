// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { ActionBus } from "../ActionBus";
import { registerCounterExampleWidget } from "./counterWidget";

beforeEach(() => {
  _resetRegistry();
  registerCounterExampleWidget();
});

test("starts at its initial value and increments on click", async () => {
  const Counter = getWidget("example.counter")!.Component;
  render(<Counter props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("5")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(screen.getByText("6")).toBeInTheDocument();
});

test("emits changed with the new count", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "setFilter", handler);
  bus.configure([{ id: "m", from: "c1", event: "changed", to: "t1", action: "setFilter" }]);
  const Counter = getWidget("example.counter")!.Component;
  render(
    <Counter
      props={{ initial: 0 }}
      ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(handler).toHaveBeenCalledWith({ count: 1 });
});

test("declares a reset action that resets to the initial value", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "c1", action: "reset" }]);
  const Counter = getWidget("example.counter")!.Component;
  render(
    <Counter
      props={{ initial: 3 }}
      ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(screen.getByText("4")).toBeInTheDocument();
  await act(async () => {
    bus.emit("emitter", "go");
  });
  expect(screen.getByText("3")).toBeInTheDocument();
});

test("declares the events/actions the ActionsPanel needs to wire it", () => {
  expect(getWidget("example.counter")!.events).toEqual(["changed"]);
  expect(getWidget("example.counter")!.actions).toEqual(["reset"]);
});
