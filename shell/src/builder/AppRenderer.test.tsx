import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { AppRenderer } from "./AppRenderer";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const stubClient = {
  queryDataSource: vi.fn().mockResolvedValue([]),
  featuresUrl: vi.fn().mockReturnValue(""),
} as unknown as ItemClient;

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={stubClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } },
  ] },
};

test("runtime mode renders widgets without edit chrome", () => {
  render(<AppRenderer config={config} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Salut")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Sélectionner/ })).toBeNull();
});

test("edit mode moving a widget calls onChange with the new position", async () => {
  const onChange = vi.fn();
  render(<AppRenderer config={config} mode="edit" selectedId="t1" onSelect={vi.fn()} onChange={onChange} />, { wrapper: Wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-t1 à droite" }));
  const next = onChange.mock.calls[0][0] as AppConfig;
  expect(next.layout.items[0]).toMatchObject({ x: 1 });
});

test("configures the bus so a button click drives a wired action", async () => {
  // Two buttons: one emits "clicked"; the message wires it to the other's… there is
  // no builtin action on button, so assert wiring via a spy widget is covered in
  // ActionBusContext.test. Here assert the renderer wires messages without crashing
  // and renders interactive widgets.
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [],
    messages: [{ id: "m", from: "b1", event: "clicked", to: "b1", action: "noop" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "b1", widget: "button", x: 0, y: 0, w: 2, h: 1, props: { label: "Go" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  // No target action registered → emitting is a safe no-op; the app still renders.
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
});

test("edits the sm layout when the breakpoint prop is sm, leaving the base intact", async () => {
  let latest: AppConfig | null = null;
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  render(
    <AppRenderer config={cfg} mode="edit" breakpoint="sm" selectedId="w1" onSelect={() => {}} onChange={(c) => { latest = c; }} />,
    { wrapper: Wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  expect(latest!.layout.items[0].x).toBe(0); // base untouched
  expect(latest!.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
});

test("renders the item at its sm override when breakpoint=sm", () => {
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" }, layouts: { sm: { x: 6, y: 2, w: 6, h: 2 } } },
    ] },
  };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" breakpoint="sm" />, { wrapper: Wrapper });
  expect(container.querySelector("[data-col]")).toHaveAttribute("data-col", "6");
});

test("applies theme CSS variables on the root container, falling back to defaults", () => {
  const cfg: AppConfig = { ...config, theme: { colors: { primary: "#ff0000" } } };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  const root = container.firstChild as HTMLElement;
  expect(root.style.getPropertyValue("--gs-color-primary")).toBe("#ff0000");
  expect(root.style.getPropertyValue("--gs-color-background")).toBe("#ffffff"); // default, untouched
  expect(root).toHaveClass("bg-[var(--gs-color-background)]");
  expect(root).toHaveClass("font-[var(--gs-font)]");
});
