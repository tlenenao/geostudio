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

// --- Contrat DOM v1 (L10, AUD-110) ---------------------------------------------------------
type V1Element = HTMLElement & {
  variables: Record<string, unknown>;
  theme: unknown;
  mode: string;
  breakpoint: unknown;
  sdkVersion: number;
  setVariable: (name: string, value: unknown) => void;
  setFilter: (sourceId: string, query: Record<string, unknown>) => void;
};

test("contrat v1 : assigne variables/theme/mode/breakpoint/sdkVersion", () => {
  const WcHost = makeWcHost(manifest);
  const ctx = {
    mode: "preview",
    variables: { region: "nord" },
    theme: { colors: {} },
    breakpoint: "md",
  } as unknown as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as V1Element;
  expect(el.variables).toEqual({ region: "nord" });
  expect(el.theme).toEqual({ colors: {} });
  expect(el.mode).toBe("preview");
  expect(el.breakpoint).toBe("md");
  expect(el.sdkVersion).toBe(1);
});

test("contrat v1 : setVariable écrit une variable connue, ignore (avec avertissement) une inconnue", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const setVariable = vi.fn();
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "runtime", variables: { region: "nord" }, setVariable } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as V1Element;
  el.setVariable("region", "sud");
  el.setVariable("inconnue", 1);
  expect(setVariable).toHaveBeenCalledTimes(1);
  expect(setVariable).toHaveBeenCalledWith("region", "sud");
  expect(warn).toHaveBeenCalled();
  warn.mockRestore();
});

test("contrat v1 : setVariable/setFilter sont inertes en mode edit", () => {
  const setVariable = vi.fn();
  const setFilter = vi.fn();
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "edit", variables: { region: "" }, setVariable, setFilter } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as V1Element;
  el.setVariable("region", "sud");
  el.setFilter("ds1", { a: 1 });
  expect(setVariable).not.toHaveBeenCalled();
  expect(setFilter).not.toHaveBeenCalled();
});

test("contrat v1 : setFilter relaie vers le host en runtime et lit le contexte courant", () => {
  const first = vi.fn();
  const second = vi.fn();
  const WcHost = makeWcHost(manifest);
  const { container, rerender } = render(
    <WcHost props={{}} ctx={{ mode: "runtime", setFilter: first } as WidgetContext} />,
  );
  const el = container.querySelector("test-wc-host-widget") as V1Element;
  rerender(<WcHost props={{}} ctx={{ mode: "runtime", setFilter: second } as WidgetContext} />);
  el.setFilter("ds1", { zone: "A" });
  expect(first).not.toHaveBeenCalled();
  expect(second).toHaveBeenCalledWith("ds1", { zone: "A" });
});

test("contrat v1 : gs:ready est émis une seule fois, après l'assignation des propriétés", () => {
  const seen: Array<{ sdkVersion: unknown; detail: unknown }> = [];
  class ReadyWidget extends HTMLElement {
    connectedCallback() {
      this.addEventListener("gs:ready", (e) =>
        seen.push({
          sdkVersion: (this as unknown as V1Element).sdkVersion,
          detail: (e as CustomEvent).detail,
        }),
      );
    }
  }
  if (!customElements.get("test-wc-ready-widget")) {
    customElements.define("test-wc-ready-widget", ReadyWidget);
  }
  const WcHost = makeWcHost({ ...manifest, tag: "test-wc-ready-widget" });
  const { rerender } = render(<WcHost props={{}} ctx={{ mode: "runtime" } as WidgetContext} />);
  rerender(<WcHost props={{ a: 1 }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(seen).toEqual([{ sdkVersion: 1, detail: { sdkVersion: 1 } }]);
});
