// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
  HeatmapChart,
  GaugeChart,
  BoxplotChart,
  CandlestickChart,
  FunnelChart,
  SankeyChart,
  TreemapChart,
  SunburstChart,
} from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  VisualMapComponent,
  TitleComponent,
  ToolboxComponent,
  PolarComponent,
  DatasetComponent,
  MarkLineComponent,
  MarkAreaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

// Register a broad set once so the config-driven Chart widget (and the raw
// "advanced option" escape hatch) can reach most panel families.
echarts.use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
  HeatmapChart,
  GaugeChart,
  BoxplotChart,
  CandlestickChart,
  FunnelChart,
  SankeyChart,
  TreemapChart,
  SunburstChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  VisualMapComponent,
  TitleComponent,
  ToolboxComponent,
  PolarComponent,
  DatasetComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

export type { EChartsOption };

function seriesList(option: EChartsOption): { type?: string }[] {
  const s = option.series;
  if (Array.isArray(s)) return s as { type?: string }[];
  return s ? [s as { type?: string }] : [];
}

// Thin React wrapper: owns the ECharts instance, keeps it sized to its box, and
// disposes on unmount. This is the only module that pulls in echarts, so the
// Chart widget lazy-loads it (and unit tests mock it).
export function EChart({
  option,
  className,
  onClick,
}: {
  option: EChartsOption;
  className?: string;
  onClick?: (params: {
    name?: string;
    value?: unknown;
    dataType?: string;
    data?: Record<string, unknown>;
    treePathInfo?: { name: string }[];
  }) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onClickRef = useRef(onClick);
  useEffect(() => {
    onClickRef.current = onClick;
  }, [onClick]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    chart.on("click", (params) =>
      onClickRef.current?.(
        params as {
          name?: string;
          value?: unknown;
          dataType?: string;
          data?: Record<string, unknown>;
          treePathInfo?: { name: string }[];
        },
      ),
    );
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  const series = seriesList(option);
  return (
    <div
      ref={containerRef}
      data-testid="echart"
      data-chart-type={series[0]?.type ?? ""}
      data-chart-series={series.length}
      className={className ?? "h-full w-full"}
    />
  );
}
