// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("button emits clicked to the wired action", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "run", handler);
  bus.configure([{ id: "m", from: "btn1", event: "clicked", to: "sink", action: "run" }]);
  const Button = getWidget("button")!.Component;
  render(
    <Button
      props={{ label: "Go" }}
      ctx={{ mode: "runtime", bus, widgetId: "btn1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(handler).toHaveBeenCalled();
});

test("button declares a clicked event", () => {
  expect(getWidget("button")!.events).toContain("clicked");
});

test("button uses the primary color and radius theme tokens", () => {
  const Button = getWidget("button")!.Component;
  render(<Button props={{ label: "Go" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByRole("button", { name: "Go" })).toHaveClass(
    "bg-[var(--gs-color-primary)]",
    "rounded-[var(--gs-radius)]",
  );
});

test("button with a javascript: href does not open a window (AUD-064)", async () => {
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  const Button = getWidget("button")!.Component;
  render(
    <Button
      props={{ label: "Go", href: "javascript:alert(1)" }}
      ctx={{ mode: "runtime", bus: new ActionBus(), widgetId: "b" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(openSpy).not.toHaveBeenCalled();
  openSpy.mockRestore();
});

test("button with a https href opens it (AUD-064)", async () => {
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  const Button = getWidget("button")!.Component;
  render(
    <Button
      props={{ label: "Go", href: "https://example.com" }}
      ctx={{ mode: "runtime", bus: new ActionBus(), widgetId: "b" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(openSpy).toHaveBeenCalledWith("https://example.com", "_blank", "noopener");
  openSpy.mockRestore();
});
