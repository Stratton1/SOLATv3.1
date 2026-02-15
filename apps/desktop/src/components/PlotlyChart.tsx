/**
 * Shared Plotly wrapper using the finance partial bundle.
 *
 * Stability fixes for known regressions:
 * - uirevision preserves user pan/zoom state across data updates
 * - onRelayout callback for detecting user pan/zoom events
 * - Keeps last-known-good data to prevent white-out on empty re-render
 * - Range validation prevents NaN/Infinity layout values
 */

import { useMemo, useCallback, useRef } from "react";
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
  onRelayout?: (event: Plotly.PlotRelayoutEvent) => void;
  /** Stable identifier — preserves user view state across data updates */
  uirevision?: string | number;
}

/** Sanitize axis range — strip NaN/Infinity to let Plotly auto-range */
function cleanRange(
  range: [Plotly.Datum, Plotly.Datum] | undefined
): [Plotly.Datum, Plotly.Datum] | undefined {
  if (!range || range.length < 2) return undefined;
  for (const v of range) {
    if (typeof v === "number" && (!isFinite(v) || isNaN(v))) return undefined;
  }
  return range;
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
  onRelayout,
  uirevision = "stable",
}: PlotlyChartProps) {
  const mergedLayout = useMemo(() => {
    const xaxis = { ...DEFAULT_AXIS, ...layout?.xaxis };
    const yaxis = { ...DEFAULT_AXIS, ...layout?.yaxis };

    // Validate ranges to prevent chart crash
    if (xaxis.range) xaxis.range = cleanRange(xaxis.range as [Plotly.Datum, Plotly.Datum]);
    if (yaxis.range) yaxis.range = cleanRange(yaxis.range as [Plotly.Datum, Plotly.Datum]);

    return {
      paper_bgcolor: "transparent",
      plot_bgcolor: "#ffffff",
      font: DEFAULT_FONT,
      margin: { l: 50, r: 20, t: 10, b: 30 },
      showlegend: false,
      hovermode: "x unified" as const,
      dragmode: "pan" as const,
      ...layout,
      xaxis,
      yaxis,
      // uirevision is critical — preserves user zoom/pan while data updates
      uirevision,
    };
  }, [layout, uirevision]);

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

  // Keep reference to last-known-good data to prevent blank chart
  const lastDataRef = useRef<Plotly.Data[]>(data);
  if (data.length > 0) {
    lastDataRef.current = data;
  }
  const stableData = data.length > 0 ? data : lastDataRef.current;

  const handleRelayout = useCallback(
    (event: Plotly.PlotRelayoutEvent) => {
      onRelayout?.(event);
    },
    [onRelayout]
  );

  return (
    <Plot
      data={stableData}
      layout={mergedLayout}
      config={mergedConfig}
      style={{ width: "100%", height: "100%", ...style }}
      className={className}
      useResizeHandler={useResizeHandler}
      onClick={onClick}
      onHover={onHover}
      onRelayout={handleRelayout}
    />
  );
}
