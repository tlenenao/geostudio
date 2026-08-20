// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { registerDateRangeFilterWidget } from "./dateRangeFilter";
import type { WidgetContext } from "../registry";

beforeEach(() => {
  _resetRegistry();
  registerDateRangeFilterWidget();
});

function TimeRangeProbe() {
  const ctx = useAnalyticsContext();
  return <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
}

test("registers with no events/actions (a global control, not a bus-wired source filter)", () => {
  const def = getWidget("dateRangeFilter")!;
  expect(def.events).toBeUndefined();
  expect(def.actions).toBeUndefined();
});

test("sets the time range when both dates are filled, only when interactions is auto", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilter props={{ label: "Période" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(await screen.findByText("timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

test("is a no-op when interactions is manual", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="manual">
      <DateRangeFilter props={{ label: "Période" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});
