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

test("fires the action when the condition evaluates truthy against the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.nom == 'A'" }]);
  bus.emit("filter1", "changed", { nom: "A" });
  expect(handler).toHaveBeenCalledWith({ nom: "A" });
});

test("does not fire the action when the condition evaluates falsy against the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.nom == 'A'" }]);
  bus.emit("filter1", "changed", { nom: "B" });
  expect(handler).not.toHaveBeenCalled();
});

test("a message without a condition always fires (no regression)", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter" }]);
  bus.emit("filter1", "changed", { nom: "anything" });
  expect(handler).toHaveBeenCalledWith({ nom: "anything" });
});

test("evaluates the condition against vars/user set via setContext, not just the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.setContext({ vars: { seuil: "haute" }, user: { name: "tanguy" } });
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "vars.seuil == 'haute' && user.name == 'tanguy'" }]);
  bus.emit("filter1", "changed", {});
  expect(handler).toHaveBeenCalled();
});

test("a malformed condition never throws and is treated as not matching", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.missingField.nested" }]);
  expect(() => bus.emit("filter1", "changed", { nom: "A" })).not.toThrow();
  expect(handler).not.toHaveBeenCalled();
});

test("a handler that throws does not prevent the next handler in the same emit from running", () => {
  const bus = new ActionBus();
  const failing = vi.fn(() => {
    throw new Error("boom");
  });
  const succeeding = vi.fn();
  bus.register("ext1", "reset", failing);
  bus.register("list1", "setFilter", succeeding);
  bus.configure([
    { id: "1", from: "btn1", event: "clicked", to: "ext1", action: "reset" },
    { id: "2", from: "btn1", event: "clicked", to: "list1", action: "setFilter" },
  ]);
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => bus.emit("btn1", "clicked", {})).not.toThrow();
  expect(succeeding).toHaveBeenCalled();
  expect(consoleError).toHaveBeenCalled();
  consoleError.mockRestore();
});
