import { expect, test, vi } from "vitest";
import { ActionBus } from "./ActionBus";

test("emits an event to the wired target action", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter" }]);
  bus.emit("filter1", "changed", { nom: "A" });
  expect(handler).toHaveBeenCalledWith({ nom: "A" });
});

test("does nothing when no message wires the event", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([]);
  bus.emit("filter1", "changed", {});
  expect(handler).not.toHaveBeenCalled();
});

test("fans one event out to multiple target actions", () => {
  const bus = new ActionBus();
  const fly = vi.fn();
  const filter = vi.fn();
  bus.register("map1", "flyTo", fly);
  bus.register("list1", "setFilter", filter);
  bus.configure([
    { id: "1", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" },
    { id: "2", from: "list1", event: "itemSelected", to: "list1", action: "setFilter" },
  ]);
  bus.emit("list1", "itemSelected", { id: 7 });
  expect(fly).toHaveBeenCalledWith({ id: 7 });
  expect(filter).toHaveBeenCalledWith({ id: 7 });
});

test("the unregister callback removes the handler", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  const off = bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m", from: "f", event: "changed", to: "list1", action: "setFilter" }]);
  off();
  bus.emit("f", "changed", {});
  expect(handler).not.toHaveBeenCalled();
});

test("reconfigure replaces the previous wiring", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "a", from: "f", event: "changed", to: "list1", action: "setFilter" }]);
  bus.configure([]);
  bus.emit("f", "changed", {});
  expect(handler).not.toHaveBeenCalled();
});
