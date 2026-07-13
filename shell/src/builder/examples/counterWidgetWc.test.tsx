import { act, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { ActionBus } from "../ActionBus";
import { registerCounterWcExampleWidget } from "./counterWidgetWc";
import type { GsCounter } from "./counterWidgetWc";
import type { WidgetContext } from "../registry";

beforeEach(() => {
  _resetRegistry();
  registerCounterWcExampleWidget();
});

test("starts at its initial value and increments on click", async () => {
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("5");
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("6");
});

test("emits changed with the new count", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "setFilter", handler);
  bus.configure([{ id: "m", from: "c1", event: "changed", to: "t1", action: "setFilter" }]);
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 0 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  expect(handler).toHaveBeenCalledWith({ count: 1 });
});

test("declares a reset action that resets to the initial value", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "c1", action: "reset" }]);
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 3 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("4");
  await act(async () => {
    bus.emit("emitter", "go");
  });
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("3");
});

test("declares the events/actions the ActionsPanel needs to wire it", () => {
  expect(getWidget("example.counter-wc")!.events).toEqual(["changed"]);
  expect(getWidget("example.counter-wc")!.actions).toEqual(["reset"]);
});
