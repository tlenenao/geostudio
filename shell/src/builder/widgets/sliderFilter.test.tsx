// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerSliderFilterWidget } from "./sliderFilter";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerSliderFilterWidget(); });

function CrossFilterProbe() {
  const ctx = useAnalyticsContext();
  return <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>;
}

function renderSlider(queryDataSource = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SliderFilter = getWidget("sliderFilter")!.Component;
  const ctx = {
    mode: "runtime", widgetId: "w1",
    data: { loading: false, error: false, records: [], datasetId: "ds-1" },
  } as unknown as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SliderFilter props={{ dataSourceId: "src-1", field: "score", label: "Score" }} ctx={ctx} />
          <CrossFilterProbe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("shows a discreet message when not bound to a dataset source", () => {
  const queryDataSource = vi.fn();
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SliderFilter = getWidget("sliderFilter")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SliderFilter props={{ dataSourceId: "", field: "", label: "Filtrer" }} ctx={{ mode: "runtime" } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/Liez ce filtre/)).toBeInTheDocument();
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("fetches min/max via a two-measure statistics query and renders the bounds", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  expect(await screen.findByText("Score (10 – 90)")).toBeInTheDocument();
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    type: "statistics", datasetId: "ds-1",
    query: { measures: [{ field: "score", agg: "min", label: "min" }, { field: "score", agg: "max", label: "max" }] },
  }));
});

test("moving the min handle sets a range cross-filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  const minInput = await screen.findByLabelText("Borne minimale") as HTMLInputElement;
  fireEvent.change(minInput, { target: { value: "50" } });
  expect(await screen.findByText(/"value":\{"from":"50","to":"90"\}/)).toBeInTheDocument();
});

test("moving back to the full bounds clears the filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  const minInput = await screen.findByLabelText("Borne minimale") as HTMLInputElement;
  fireEvent.change(minInput, { target: { value: "50" } });
  await screen.findByText(/"from":"50"/);
  fireEvent.change(minInput, { target: { value: "10" } });
  expect(await screen.findByText("crossFilter:{}")).toBeInTheDocument();
});
