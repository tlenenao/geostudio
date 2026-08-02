// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { test, expect, vi, beforeEach, afterEach } from "vitest";
import { EChart } from "./EChart";
import { SunburstChart } from "echarts/charts";

// Mock echarts to avoid canvas rendering issues in jsdom
const { useMock } = vi.hoisted(() => ({ useMock: vi.fn() }));
vi.mock("echarts/core", () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    on: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
  })),
  use: useMock,
}));

vi.mock("echarts/charts", () => ({
  BarChart: {},
  LineChart: {},
  PieChart: {},
  ScatterChart: {},
  RadarChart: {},
  HeatmapChart: {},
  GaugeChart: {},
  BoxplotChart: {},
  CandlestickChart: {},
  FunnelChart: {},
  SankeyChart: {},
  TreemapChart: {},
  SunburstChart: {},
}));

vi.mock("echarts/components", () => ({
  TooltipComponent: {},
  LegendComponent: {},
  GridComponent: {},
  DataZoomComponent: {},
  VisualMapComponent: {},
  TitleComponent: {},
  ToolboxComponent: {},
  PolarComponent: {},
  DatasetComponent: {},
  MarkLineComponent: {},
  MarkAreaComponent: {},
}));

vi.mock("echarts/renderers", () => ({
  CanvasRenderer: {},
}));

// EChart.tsx calls `new ResizeObserver(...)` unconditionally (no guard), unlike
// AppRenderer.tsx which relies on jsdom's lack of ResizeObserver to keep its
// breakpoint auto-detection at "lg" during tests. Stub it locally to this file
// only, so we don't flip that guard for the rest of the suite.
beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders a sunburst option without throwing (SunburstChart must be registered)", () => {
  const { getByTestId } = render(
    <EChart option={{ series: [{ type: "sunburst", data: [{ name: "A", value: 1 }] }] }} />,
  );
  expect(getByTestId("echart")).toHaveAttribute("data-chart-type", "sunburst");
});

test("registers SunburstChart with echarts.use", () => {
  render(
    <EChart option={{ series: [{ type: "sunburst", data: [{ name: "A", value: 1 }] }] }} />,
  );
  // NB: each chart-type mock is a bare `{}`, so they are all deep-equal to one
  // another — `toHaveBeenCalledWith(expect.arrayContaining(...))` (structural
  // equality) would pass even if SunburstChart were never registered, as long
  // as *some* other `{}` chart mock was in the array. Use `toContain`, which
  // checks reference identity, to genuinely discriminate.
  expect(useMock).toHaveBeenCalledTimes(1);
  expect(useMock.mock.calls[0][0]).toContain(SunburstChart);
});
