// SPDX-License-Identifier: Apache-2.0
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ActionBus } from "../ActionBus";
import { makeWcHost } from "./WcHost";
import type { WcWidgetManifest } from "./manifest";
import type { WidgetContext } from "../registry";

class TestWcWidget extends HTMLElement {
  props?: unknown;
  data?: unknown;
  user?: unknown;
  navigate?: unknown;
  resetCalls: unknown[] = [];
  reset(payload?: unknown) {
    this.resetCalls.push(payload);
  }
}
if (!customElements.get("test-wc-host-widget")) {
  customElements.define("test-wc-host-widget", TestWcWidget);
}

const manifest: WcWidgetManifest = {
  type: "test.wc-host",
  tag: "test-wc-host-widget",
  label: "Test WcHost",
  props: [{ name: "initial", type: "number", label: "Initial", default: 0 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 2, h: 2 },
};

afterEach(cleanup);

test("mounts the custom element inside its container", () => {
  const WcHost = makeWcHost(manifest);
  const { container } = render(
    <WcHost props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  expect(container.querySelector("test-wc-host-widget")).not.toBeNull();
});

test("assigns props/data/user/navigate as DOM properties, not attributes", () => {
  const WcHost = makeWcHost(manifest);
  const navigate = vi.fn();
  const ctx = {
    mode: "runtime",
    data: { loading: false, error: false, records: [] },
    user: { name: "alice" },
    navigate,
  } as unknown as WidgetContext;
  const { container } = render(<WcHost props={{ initial: 5 }} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  expect(el.props).toEqual({ initial: 5 });
  expect(el.data).toEqual(ctx.data);
  expect(el.user).toEqual({ name: "alice" });
  expect(el.navigate).toBe(navigate);
  expect(el.getAttribute("props")).toBeNull();
  expect(el.getAttribute("data")).toBeNull();
});

test("re-assigns props on every prop change", () => {
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container, rerender } = render(<WcHost props={{ initial: 1 }} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  rerender(<WcHost props={{ initial: 2 }} ctx={ctx} />);
  expect(el.props).toEqual({ initial: 2 });
});

test("removes the element from the DOM on unmount", () => {
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container, unmount } = render(<WcHost props={{}} ctx={ctx} />);
  expect(container.querySelector("test-wc-host-widget")).not.toBeNull();
  unmount();
  expect(container.querySelector("test-wc-host-widget")).toBeNull();
});

test("relays a CustomEvent dispatched by the element to bus.emit", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "onChanged", handler);
  bus.configure([{ id: "m", from: "w1", event: "changed", to: "t1", action: "onChanged" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  el.dispatchEvent(new CustomEvent("changed", { detail: { count: 3 } }));
  expect(handler).toHaveBeenCalledWith({ count: 3 });
});

test("invoking a bus action calls the matching public method on the element", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "w1", action: "reset" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  act(() => {
    bus.emit("emitter", "go", { to: 0 });
  });
  expect(el.resetCalls).toEqual([{ to: 0 }]);
});

test("unregisters the bus action and stops relaying events on unmount", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "w1", action: "reset" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container, unmount } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  unmount();
  bus.emit("emitter", "go");
  expect(el.resetCalls).toEqual([]);
});
