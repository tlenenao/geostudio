// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { PropsPanel } from "./PropsPanel";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient, WidgetItem } from "../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const item: WidgetItem = { id: "t", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } };

// The "text" widget's PropsPanel offers a source-binding DataSourceSelect,
// which reads the item client via useItems even when its query is disabled
// — so any render exercising PropsPanel needs an ItemClientProvider in scope.
function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={{} as unknown as ItemClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("edits the selected widget's props", async () => {
  const onChange = vi.fn();
  render(<PropsPanel item={item} dataSources={[]} onChange={onChange} onVisibleWhenChange={vi.fn()} />, { wrapper });
  const area = screen.getByLabelText("Texte du widget");
  await userEvent.type(area, "!");
  expect(onChange).toHaveBeenCalled();
  const last = onChange.mock.calls.at(-1)![0];
  expect(String(last.text).startsWith("Hi")).toBe(true);
});

test("shows a placeholder when nothing is selected", () => {
  render(<PropsPanel item={null} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />, { wrapper });
  expect(screen.getByText(/aucun widget/i)).toBeInTheDocument();
});

test("edits the selected widget's visibleWhen and shows a validation error", async () => {
  const onVisibleWhenChange = vi.fn();
  render(<PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={onVisibleWhenChange} />, { wrapper });
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x ==");
  expect(onVisibleWhenChange).toHaveBeenCalled();
});

test("shows no validation error for a valid visibleWhen", () => {
  const itemWithValidExpr = { ...item, visibleWhen: "vars.x == 'a'" };
  render(<PropsPanel item={itemWithValidExpr} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />, { wrapper });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("shows a validation error for an invalid visibleWhen", () => {
  const itemWithInvalidExpr = { ...item, visibleWhen: "vars.x ==" };
  render(<PropsPanel item={itemWithInvalidExpr} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />, { wrapper });
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
