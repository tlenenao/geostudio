import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ActionBus } from "./ActionBus";
import { useBusAction } from "./ActionBusContext";

test("useBusAction registers a live handler and cleans up on unmount", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "a", event: "ping", to: "b", action: "pong" }]);
  const spy = vi.fn();

  function Receiver({ n }: { n: number }) {
    useBusAction(bus, "b", "pong", () => spy(n));
    return null;
  }

  const { rerender, unmount } = render(<Receiver n={1} />);
  bus.emit("a", "ping");
  expect(spy).toHaveBeenLastCalledWith(1);

  // Latest handler is used after a re-render (no stale closure).
  rerender(<Receiver n={2} />);
  bus.emit("a", "ping");
  expect(spy).toHaveBeenLastCalledWith(2);

  // Handler is removed on unmount.
  unmount();
  spy.mockClear();
  bus.emit("a", "ping");
  expect(spy).not.toHaveBeenCalled();
});

test("emitting from a button invokes the wired action across two widgets", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "btn", event: "clicked", to: "sink", action: "run" }]);
  const spy = vi.fn();

  function Emitter() {
    return <button onClick={() => bus.emit("btn", "clicked", { ok: true })}>go</button>;
  }
  function Sink() {
    useBusAction(bus, "sink", "run", (p) => spy(p));
    return null;
  }
  render(<><Emitter /><Sink /></>);
  await userEvent.click(screen.getByText("go"));
  expect(spy).toHaveBeenCalledWith({ ok: true });
});
