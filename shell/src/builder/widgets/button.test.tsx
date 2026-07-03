import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("button emits clicked to the wired action", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "run", handler);
  bus.configure([{ id: "m", from: "btn1", event: "clicked", to: "sink", action: "run" }]);
  const Button = getWidget("button")!.Component;
  render(<Button props={{ label: "Go" }} ctx={{ mode: "runtime", bus, widgetId: "btn1" } as WidgetContext} />);
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(handler).toHaveBeenCalled();
});

test("button declares a clicked event", () => {
  expect(getWidget("button")!.events).toContain("clicked");
});
