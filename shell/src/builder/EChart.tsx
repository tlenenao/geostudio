// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useMemo, useRef, useState } from "react";
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
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import { t } from "../i18n";
import "../i18n/domains/widgets";
import { chartTable } from "./chartTable";

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
  AriaComponent,
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
    // AUD-114 : description générée par ECharts + motifs (decal) — la couleur n'est plus
    // la seule voie de distinction entre séries.
    chartRef.current?.setOption(
      { aria: { enabled: true, decal: { show: true } }, ...option },
      true,
    );
  }, [option]);

  const series = seriesList(option);
  const table = useMemo(() => chartTable(option), [option]);
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  return (
    <div className={`flex flex-col ${className ?? "h-full w-full"}`}>
      <div
        ref={containerRef}
        role="img"
        aria-label={t("echart.ariaLabel", {
          type: series[0]?.type ?? "",
          count: series.length,
        })}
        data-testid="echart"
        data-chart-type={series[0]?.type ?? ""}
        data-chart-series={series.length}
        className="min-h-0 w-full flex-1"
      />
      {table && (
        <div className="text-xs">
          <button
            type="button"
            className="text-accent hover:underline"
            aria-expanded={showTable}
            aria-controls={tableId}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? t("echart.hideTable") : t("echart.showTable")}
          </button>
          <div id={tableId} hidden={!showTable} className="max-h-40 overflow-auto">
            {showTable && (
              <table className="w-full text-left">
                <caption className="sr-only">{t("echart.tableCaption")}</caption>
                <thead>
                  <tr>
                    {table.head.map((h, i) => (
                      <th key={i} scope="col">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((r, i) => (
                    <tr key={i}>
                      <th scope="row" className="font-normal">
                        {onClick ? (
                          <button
                            type="button"
                            className="text-accent hover:underline"
                            aria-label={t("echart.selectCategory", { name: r[0] })}
                            onClick={() => onClick({ name: r[0], dataType: "main" })}
                          >
                            {r[0]}
                          </button>
                        ) : (
                          r[0]
                        )}
                      </th>
                      {r.slice(1).map((c, j) => (
                        <td key={j}>{c}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
