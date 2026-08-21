// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { ItemClient } from "../../api/types";
import type { AuthState } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetItem } from "../../api/types";

// WidgetHost (mounted by GridCanvas, directly or via the nested LayoutEditor)
// calls useAuth(), which requires an <AuthProvider> ancestor outside of
// tests. Mocked the same way WidgetHost.test.tsx / LayoutEditor.test.tsx do
// it, so the tabs widget can be rendered standalone.
const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "tanguy",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

// The "text" widget's PropsPanel offers a source-binding DataSourceSelect,
// which reads the item client via useItems even when its query is disabled
// — so any render that selects an item inside the nested LayoutEditor needs
// an ItemClientProvider in scope (mirrors LayoutEditor.test.tsx's wrapper).
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

test("runtime: shows the first tab's content by default and switches on click", async () => {
  const tabA: WidgetItem = {
    id: "a",
    widget: "text",
    x: 0,
    y: 0,
    w: 4,
    h: 2,
    props: { text: "Contenu A" },
  };
  const tabB: WidgetItem = {
    id: "b",
    widget: "text",
    x: 0,
    y: 0,
    w: 4,
    h: 2,
    props: { text: "Contenu B" },
  };
  const Tabs = getWidget("tabs")!.Component;
  render(
    <Tabs
      props={{
        tabs: [
          { id: "t1", label: "Onglet 1", items: [tabA] },
          { id: "t2", label: "Onglet 2", items: [tabB] },
        ],
      }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
    { wrapper },
  );
  expect(screen.getByText("Contenu A")).toBeInTheDocument();
  expect(screen.queryByText("Contenu B")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Onglet 2" }));
  expect(screen.queryByText("Contenu A")).not.toBeInTheDocument();
  expect(screen.getByText("Contenu B")).toBeInTheDocument();
});

test("edit mode renders statically without an interactive tab bar switch", () => {
  const tabA: WidgetItem = {
    id: "a",
    widget: "text",
    x: 0,
    y: 0,
    w: 4,
    h: 2,
    props: { text: "Contenu A" },
  };
  const Tabs = getWidget("tabs")!.Component;
  render(
    <Tabs
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [tabA] }] }}
      ctx={{ mode: "edit" } as WidgetContext}
    />,
  );
  expect(screen.getByText("Onglet 1")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onglet 1" })).not.toBeInTheDocument();
});

test("PropsPanel adds a tab, selects it, and edits its label", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }] }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un onglet" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs).toHaveLength(2);
  expect(tabs[1].label).toBe("Onglet 2");
});

test("PropsPanel refuses to remove the last remaining tab", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }] }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Supprimer l'onglet Onglet 1" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("PropsPanel reorders tabs with the up/down buttons", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{
        tabs: [
          { id: "t1", label: "Onglet 1", items: [] },
          { id: "t2", label: "Onglet 2", items: [] },
        ],
      }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Descendre l'onglet Onglet 1" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs as Array<{ label: string }>;
  expect(tabs.map((t) => t.label)).toEqual(["Onglet 2", "Onglet 1"]);
});

test("PropsPanel edits only the active tab's items, switchable via the tab selector", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  const { rerender } = render(
    <Panel
      props={{
        tabs: [
          { id: "t1", label: "Onglet 1", items: [] },
          { id: "t2", label: "Onglet 2", items: [] },
        ],
      }}
      dataSources={[]}
      onChange={onChange}
    />,
    { wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  let tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs[0].items).toHaveLength(1);
  expect(tabs[1].items).toHaveLength(0);

  rerender(<Panel props={{ tabs }} dataSources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner l'onglet Onglet 2" }));
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs[0].items).toHaveLength(1);
  expect(tabs[1].items).toHaveLength(1);
});
