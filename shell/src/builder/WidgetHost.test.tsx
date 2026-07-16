// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { registerWidget, _resetRegistry } from "./registry";
import { WidgetHost } from "./WidgetHost";
import type { WidgetItem } from "../api/types";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

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

test("hides a widget in runtime mode when visibleWhen evaluates to false", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 2" }} mode="runtime" />);
  expect(screen.queryByText("visible-content")).not.toBeInTheDocument();
});

test("shows a widget in runtime mode when visibleWhen evaluates to true", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 1" }} mode="runtime" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});

test("always shows a widget in edit mode regardless of visibleWhen", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 2" }} mode="edit" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});

test("shows a widget when visibleWhen is absent", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={item("ok")} mode="runtime" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});

test("resolves an { $expr } prop value before passing it to the widget", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: { $expr: "1 + 1" } })} mode="runtime" />);
  expect(screen.getByText("value:2")).toBeInTheDocument();
});

test("leaves a plain (non-$expr) prop value unchanged", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: "static" })} mode="runtime" />);
  expect(screen.getByText("value:static")).toBeInTheDocument();
});

test("resolves { $expr } props in edit mode too, unlike visibleWhen", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: { $expr: "1 + 1" } })} mode="edit" />);
  expect(screen.getByText("value:2")).toBeInTheDocument();
});
