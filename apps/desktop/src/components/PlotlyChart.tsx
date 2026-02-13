/**
 * Shared Plotly wrapper using the finance partial bundle.
 * Provides consistent theming and responsive behavior.
 */

import { useMemo } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-finance-dist";

const Plot = createPlotlyComponent(Plotly);

const DEFAULT_FONT = {
  family: "'JetBrains Mono', monospace",
  size: 10,
  color: "#5f6775",
};

const DEFAULT_AXIS = {
  gridcolor: "#e8ebf0",
  linecolor: "#d5d9e0",
  zerolinecolor: "#e8ebf0",
};

interface PlotlyChartProps {
  data: Plotly.Data[];
  layout?: Partial<Plotly.Layout>;
  config?: Partial<Plotly.Config>;
  style?: React.CSSProperties;
  className?: string;
  useResizeHandler?: boolean;
  onClick?: (event: Plotly.PlotMouseEvent) => void;
  onHover?: (event: Plotly.PlotHoverEvent) => void;
}

export function PlotlyChart({
  data,
  layout,
  config,
  style,
  className,
  useResizeHandler = true,
  onClick,
  onHover,
}: PlotlyChartProps) {
  const mergedLayout = useMemo(
    () => ({
      paper_bgcolor: "transparent",
      plot_bgcolor: "#ffffff",
      font: DEFAULT_FONT,
      margin: { l: 50, r: 20, t: 10, b: 30 },
      xaxis: { ...DEFAULT_AXIS, ...layout?.xaxis },
      yaxis: { ...DEFAULT_AXIS, ...layout?.yaxis },
      showlegend: false,
      hovermode: "x unified" as const,
      dragmode: "pan" as const,
      ...layout,
      // Re-apply axis merges after spread
      ...(layout?.xaxis && { xaxis: { ...DEFAULT_AXIS, ...layout.xaxis } }),
      ...(layout?.yaxis && { yaxis: { ...DEFAULT_AXIS, ...layout.yaxis } }),
    }),
    [layout]
  );

  const mergedConfig = useMemo(
    () => ({
      responsive: true,
      displaylogo: false,
      displayModeBar: false as const,
      scrollZoom: true,
      ...config,
    }),
    [config]
  );

  return (
    <Plot
      data={data}
      layout={mergedLayout}
      config={mergedConfig}
      style={{ width: "100%", height: "100%", ...style }}
      className={className}
      useResizeHandler={useResizeHandler}
      onClick={onClick}
      onHover={onHover}
    />
  );
}
