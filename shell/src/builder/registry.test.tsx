// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { registerWidget, getWidget, listWidgets, _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import type { WidgetContext } from "./registry";

const ctx = { mode: "runtime" } as WidgetContext;

beforeEach(() => _resetRegistry());

test("registers and retrieves a widget definition", () => {
  registerWidget({
    type: "demo",
    label: "Demo",
    defaultProps: { a: 1 },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />,
    Component: () => <div>demo</div>,
  });
  expect(getWidget("demo")?.label).toBe("Demo");
  expect(listWidgets().map((w) => w.type)).toEqual(["demo"]);
});

test("builtin widgets render their props", () => {
  registerBuiltinWidgets();
  const kinds = listWidgets().map((w) => w.type);
  expect(kinds).toEqual(expect.arrayContaining(["text", "image", "button"]));

  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Bonjour" }} ctx={ctx} />);
  expect(screen.getByText("Bonjour")).toBeInTheDocument();

  const Button = getWidget("button")!.Component;
  render(<Button props={{ label: "Cliquer" }} ctx={ctx} />);
  expect(screen.getByRole("button", { name: "Cliquer" })).toBeInTheDocument();

  const Image = getWidget("image")!.Component;
  render(<Image props={{ src: "http://x/y.png", alt: "Y" }} ctx={ctx} />);
  expect(screen.getByRole("img", { name: "Y" })).toHaveAttribute("src", "http://x/y.png");
});

test("registerWidget warns when a type is overwritten, but still overwrites it", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  registerWidget({
    type: "dup", label: "A", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div>a</div>,
  });
  registerWidget({
    type: "dup", label: "B", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div>b</div>,
  });
  expect(warn).toHaveBeenCalledWith(expect.stringContaining("dup"));
  expect(getWidget("dup")?.label).toBe("B");
  warn.mockRestore();
});

test("registerWidget does not warn for a brand-new type", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  registerWidget({
    type: "fresh", label: "A", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div />,
  });
  expect(warn).not.toHaveBeenCalled();
  warn.mockRestore();
});
