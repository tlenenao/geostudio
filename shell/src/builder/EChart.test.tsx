// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { test, expect, vi, beforeEach } from "vitest";
import { EChart } from "./EChart";

// Mock echarts to avoid canvas rendering issues in jsdom
vi.mock("echarts/core", () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    on: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
  })),
  use: vi.fn(),
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

test("renders a sunburst option without throwing (SunburstChart must be registered)", () => {
  const { getByTestId } = render(
    <EChart option={{ series: [{ type: "sunburst", data: [{ name: "A", value: 1 }] }] }} />,
  );
  expect(getByTestId("echart")).toHaveAttribute("data-chart-type", "sunburst");
});
