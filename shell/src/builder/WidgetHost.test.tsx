import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { registerWidget, _resetRegistry } from "./registry";
import { WidgetHost } from "./WidgetHost";
import type { WidgetItem } from "../api/types";

beforeEach(() => _resetRegistry());
afterEach(() => vi.restoreAllMocks());

const item = (widget: string, props = {}): WidgetItem => ({ id: "x", widget, x: 0, y: 0, w: 2, h: 2, props });

test("renders the registered widget", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>ok-{String(props.n)}</div> });
  render(<WidgetHost item={item("ok", { n: 7 })} mode="runtime" />);
  expect(screen.getByText("ok-7")).toBeInTheDocument();
});

test("shows a fallback for an unknown widget type", () => {
  render(<WidgetHost item={item("nope")} mode="runtime" />);
  expect(screen.getByText(/widget inconnu/i)).toBeInTheDocument();
});

test("isolates a widget that throws during render", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  registerWidget({ type: "boom", label: "Boom", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => { throw new Error("boom"); } });
  render(<WidgetHost item={item("boom")} mode="runtime" />);
  expect(screen.getByText(/erreur du widget/i)).toBeInTheDocument();
});
