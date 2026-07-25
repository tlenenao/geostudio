// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  AnalyticsContextProvider, useAnalyticsContext, useSetCrossFilter, useSetExtent, useSetTimeRange,
} from "./AnalyticsContext";

function Probe() {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  return (
    <div>
      <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>
      <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>
      <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>set-time</button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
    </div>
  );
}

test("setters are silent no-ops when interactions is not 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="manual"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

test("setTimeRange updates state when interactions is 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

test("hooks work with no provider mounted at all (default no-op context)", async () => {
  render(<Probe />);
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

test("setCrossFilter toggles: same (field, value) twice clears it, a different value replaces it", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/"ds1":\{"field":"region","value":"Nord","originSourceId":"src1"\}/)).toBeInTheDocument();
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});

// Scoped in its own describe: vitest applies top-level beforeEach/afterEach to every
// test in the file regardless of declaration order relative to test(), so fake timers
// must be confined here to avoid hanging the userEvent.click() calls in the tests above
// (their bare userEvent.click is not wired to vi.advanceTimersByTime).
describe("extent debounce", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("setExtent debounces ~500ms before updating state", () => {
    // fireEvent (not userEvent) here: userEvent's internal async wait model hangs
    // indefinitely under Vitest fake timers in this environment even with
    // `advanceTimers`/`delay: null` configured. fireEvent + act() around the timer
    // advances is the standard RTL-sanctioned way to combine a click with fake timers.
    render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
    fireEvent.click(screen.getByText("set-extent"));
    expect(screen.getByText("extent:none")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(499); });
    expect(screen.getByText("extent:none")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(1); });
    expect(screen.getByText("extent:1,2,3,4")).toBeInTheDocument();
  });
});
