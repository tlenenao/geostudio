// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerSelectFilterWidget } from "./selectFilter";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { ItemClient } from "../../api/types";

beforeEach(() => {
  _resetRegistry();
  registerSelectFilterWidget();
});

function CrossFilterProbe() {
  const ctx = useAnalyticsContext();
  return <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>;
}

function renderSelect(props: Record<string, unknown>, queryDataSource = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SelectFilter = getWidget("selectFilter")!.Component;
  const ctx = {
    mode: "runtime",
    widgetId: "w1",
    data: { loading: false, error: false, records: [], datasetId: "ds-1" },
  } as unknown as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SelectFilter
            props={{ dataSourceId: "src-1", field: "region", label: "Région", ...props }}
            ctx={ctx}
          />
          <CrossFilterProbe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client };
}

test("shows a discreet message when not bound to a dataset source", () => {
  const queryDataSource = vi.fn();
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SelectFilter = getWidget("selectFilter")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SelectFilter
            props={{ dataSourceId: "", field: "", label: "Filtrer" }}
            ctx={{ mode: "runtime" } as WidgetContext}
          />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/Liez ce filtre/)).toBeInTheDocument();
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("fetches distinct values via a groupBy statistics query and renders one checkbox per value", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  expect(await screen.findByLabelText("Nord")).toBeInTheDocument();
  expect(screen.getByLabelText("Sud")).toBeInTheDocument();
  expect(screen.getByText("Nord (3)")).toBeInTheDocument();
  expect(queryDataSource).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "statistics",
      datasetId: "ds-1",
      query: { groupBy: "region" },
    }),
  );
});

test("checking a value sets a single-element array cross-filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  await userEvent.click(await screen.findByLabelText("Nord"));
  expect(
    screen.getByText(/"ds-1":\{"field":"region","value":\["Nord"\],"originSourceId":"src-1"\}/),
  ).toBeInTheDocument();
});

test("checking two values accumulates them, unchecking the last one clears the filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  await userEvent.click(await screen.findByLabelText("Nord"));
  await userEvent.click(screen.getByLabelText("Sud"));
  expect(screen.getByText(/"value":\["Nord","Sud"\]/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Nord"));
  await userEvent.click(screen.getByLabelText("Sud"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});
