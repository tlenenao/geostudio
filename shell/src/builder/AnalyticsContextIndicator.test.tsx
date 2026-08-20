// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import {
  AnalyticsContextProvider,
  useSetCrossFilter,
  useSetExtent,
  useSetTimeRange,
} from "./AnalyticsContext";
import { AnalyticsContextIndicator } from "./AnalyticsContextIndicator";
import type { DatasetConfig } from "../api/types";
import { DatasetsContext } from "./DataContext";

function Controls() {
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  return (
    <div>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>
        set-time
      </button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
    </div>
  );
}

function renderIndicator() {
  return render(
    <AnalyticsContextProvider interactions="auto">
      <Controls />
      <AnalyticsContextIndicator />
    </AnalyticsContextProvider>,
  );
}

test("renders nothing when the context is empty", () => {
  // Deliberately not using renderIndicator(): it also mounts <Controls />,
  // whose buttons would make `container` non-empty regardless of the
  // indicator's own behaviour. This test isolates the indicator alone.
  const { container } = render(
    <AnalyticsContextProvider interactions="auto">
      <AnalyticsContextIndicator />
    </AnalyticsContextProvider>,
  );
  expect(container).toBeEmptyDOMElement();
});

test("shows a period chip with a working clear button", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText(/Période : 2026-01-01 → 2026-02-01/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Effacer la période"));
  expect(screen.queryByText(/Période :/)).not.toBeInTheDocument();
});

test("shows one chip per active cross-filter, clearing one leaves the other untouched", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Effacer le filtre region"));
  expect(screen.queryByText(/region : Nord/)).not.toBeInTheDocument();
  expect(screen.getByText(/Période :/)).toBeInTheDocument();
});

test("shows 'Tout effacer' only with 2+ active chips, and it clears everything", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.queryByText("Tout effacer")).not.toBeInTheDocument();
  await userEvent.click(screen.getByText("set-cf"));
  await userEvent.click(screen.getByText("Tout effacer"));
  expect(screen.queryByText(/Période :/)).not.toBeInTheDocument();
  expect(screen.queryByText(/region : Nord/)).not.toBeInTheDocument();
});

test("formats an array cross-filter value as a comma-joined list and a range as an arrow", async () => {
  function RangeControl() {
    const setCrossFilter = useSetCrossFilter();
    return (
      <button onClick={() => setCrossFilter("ds1", "score", { from: "10", to: "50" }, "src1")}>
        set-range
      </button>
    );
  }
  render(
    <AnalyticsContextProvider interactions="auto">
      <RangeControl />
      <AnalyticsContextIndicator />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("set-range"));
  expect(screen.getByText(/score : 10 → 50/)).toBeInTheDocument();
});

test("shows the dataset(s) a cross-filter propagates to via a declared link", async () => {
  const datasets: Record<string, DatasetConfig> = {
    ds1: {
      source: "collection",
      collectionId: "communes",
      columns: {},
      crossFilterLinks: [
        { targetDatasetId: "ds2", mode: "attribute", sourceField: "region", targetField: "region" },
      ],
    },
  };
  render(
    <DatasetsContext.Provider value={datasets}>
      <AnalyticsContextProvider interactions="auto">
        <Controls />
        <AnalyticsContextIndicator />
      </AnalyticsContextProvider>
    </DatasetsContext.Provider>,
  );
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  expect(screen.getByText(/→ ds2/)).toBeInTheDocument();
});

test("shows no propagation arrow when the dataset declares no matching link", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  expect(screen.queryByText(/→/)).not.toBeInTheDocument();
});

test("shows no propagation arrow when the declared link's mode does not match the active filter", async () => {
  const datasets: Record<string, DatasetConfig> = {
    ds1: {
      source: "collection",
      collectionId: "communes",
      columns: {},
      crossFilterLinks: [
        {
          targetDatasetId: "ds2",
          mode: "attribute",
          sourceField: "other-field",
          targetField: "region",
        },
      ],
    },
  };
  render(
    <DatasetsContext.Provider value={datasets}>
      <AnalyticsContextProvider interactions="auto">
        <Controls />
        <AnalyticsContextIndicator />
      </AnalyticsContextProvider>
    </DatasetsContext.Provider>,
  );
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  expect(screen.queryByText(/→/)).not.toBeInTheDocument();
});
