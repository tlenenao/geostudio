// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, WidgetItem } from "../api/types";
import type { AuthState } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { _resetRegistry, getWidget, registerWidget } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { LayoutEditor } from "./LayoutEditor";

// WidgetHost (mounted by GridCanvas for each item) calls useAuth(), which
// requires an <AuthProvider> ancestor outside of tests. Mocked the same way
// WidgetHost.test.tsx and AppRenderer.test.tsx do it, so LayoutEditor can be
// rendered standalone without wiring up the real OIDC provider tree.
const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

// The "text" widget's PropsPanel offers a source-binding DataSourceSelect,
// which reads the item client via useItems even when its query is disabled
// — so any render exercising a selected item's PropsPanel needs an
// ItemClientProvider in scope (mirrors PropsPanel.test.tsx's wrapper).
function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={{} as unknown as ItemClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("adds a widget from the palette, positioned below existing items, and selects it", async () => {
  const onChange = vi.fn();
  render(<LayoutEditor items={[]} onChange={onChange} dataSources={[]} breakpoint="lg" />, { wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  expect(onChange).toHaveBeenCalledTimes(1);
  const items = onChange.mock.calls[0][0] as WidgetItem[];
  expect(items).toHaveLength(1);
  expect(items[0]).toMatchObject({ widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Nouveau texte", dataSourceId: "" } });
});

test("excludes container kinds from its own palette to prevent nesting", () => {
  // registerBuiltinWidgets() may already register the real "tabs"/"modal"/"drawer"
  // kinds by the time this test runs (Tasks 5-7) — only register a stub if a kind
  // isn't present yet, so this test stays meaningful both before and after those
  // tasks land, without an "overwriting an already-registered widget type" warning.
  for (const type of ["tabs", "modal", "drawer"]) {
    if (getWidget(type)) continue;
    registerWidget({ type, label: type, defaultProps: {}, defaultSize: { w: 1, h: 1 }, PropsPanel: () => <div />, Component: () => <div /> });
  }
  render(<LayoutEditor items={[]} onChange={vi.fn()} dataSources={[]} breakpoint="lg" />, { wrapper });
  expect(screen.getByRole("button", { name: "Texte" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "tabs" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onglets" })).not.toBeInTheDocument();
});

test("selecting an item shows its PropsPanel and edits its props", async () => {
  const item: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bonjour", dataSourceId: "" } };
  const onChange = vi.fn();
  render(<LayoutEditor items={[item]} onChange={onChange} dataSources={[]} breakpoint="lg" />, { wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  expect(screen.getByLabelText("Texte du widget")).toHaveValue("Bonjour");
  await userEvent.type(screen.getByLabelText("Texte du widget"), "!");
  const items = onChange.mock.calls.at(-1)![0] as WidgetItem[];
  expect(items[0].props.text).toBe("Bonjour!");
  expect(items[0].id).toBe("a");
});

test("moving the selected item updates its position via onChange", async () => {
  const item: WidgetItem = { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {} };
  const onChange = vi.fn();
  render(<LayoutEditor items={[item]} onChange={onChange} dataSources={[]} breakpoint="lg" />, { wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a à droite" }));
  const items = onChange.mock.calls.at(-1)![0] as WidgetItem[];
  expect(items[0].x).toBe(1);
});
