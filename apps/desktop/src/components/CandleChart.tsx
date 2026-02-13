/**
 * Candlestick chart component using Plotly.js.
 *
 * Features:
 * - OHLC candlesticks
 * - Line overlays (EMA, SMA, Bollinger, Ichimoku, etc.)
 * - Signal markers (BUY/SELL arrows)
 * - Execution markers (entry/exit)
 * - SL/TP horizontal dashed lines
 * - Drawing tools (horizontal, trendline, ray, rectangle)
 * - Auto-resize
 */

import { useMemo, useCallback, useRef } from "react";
import Plotly from "plotly.js-finance-dist";
import { PlotlyChart } from "./PlotlyChart";
import { Bar, OverlayResult, Signal } from "../lib/engineClient";
import { Drawing, DrawingTool, DrawingCoord } from "../lib/drawings";

// =============================================================================
// Types
// =============================================================================

export interface Execution {
  ts: string;
  type: "ENTRY" | "EXIT";
  direction: "BUY" | "SELL";
  price: number;
  size?: number;
  bot?: string;
}

export interface SlTpLevel {
  type: "SL" | "TP";
  price: number;
  direction: "BUY" | "SELL";
  symbol?: string;
}

interface CandleChartProps {
  bars: Bar[];
  overlays?: OverlayResult[];
  signals?: Signal[];
  executions?: Execution[];
  slTpLevels?: SlTpLevel[];
  drawings?: Drawing[];
  activeTool?: DrawingTool;
  onDrawingComplete?: (drawing: Omit<Drawing, "id">) => void;
  height?: number;
  onCrosshairMove?: (time: number | null, price: number | null) => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

// Theme constants
const THEME = {
  candleUp: "#00d68f",
  candleDown: "#f45b69",
  buyGreen: "#00d68f",
  sellRed: "#f45b69",
  entryBlue: "#3d8bfd",
  exitYellow: "#f7b955",
  slRed: "#f45b69",
  tpGreen: "#00d68f",
};

// Strategy colors — 9 distinct colors for signal markers
const STRATEGY_COLORS: Record<string, string> = {
  TKCrossSniper: "#2563eb",
  KumoBreaker: "#d97706",
  ChikouConfirmer: "#7c3aed",
  KijunBouncer: "#059669",
  CloudTwist: "#0891b2",
  MomentumRider: "#db2777",
  TrendSurfer: "#ca8a04",
  ReversalHunter: "#e11d48",
  ChikouKaizen: "#6366f1",
};

function getStrategyColor(strategy: string | undefined): string {
  if (!strategy) return THEME.buyGreen;
  return STRATEGY_COLORS[strategy] ?? "#5f6775";
}

// Overlay colors — optimized for light background readability
const OVERLAY_COLORS: Record<string, string[]> = {
  ema: ["#2563eb", "#d97706", "#7c3aed", "#059669"],
  sma: ["#0891b2", "#db2777", "#ca8a04", "#059669"],
  bollinger: ["#7a8290", "#7a8290", "#7a8290"],
  ichimoku: ["#059669", "#e11d48", "#d97706", "#7a8290", "#7c3aed"],
  rsi: ["#7c3aed"],
  macd: ["#2563eb", "#e11d48", "#059669"],
  stochastic: ["#2563eb", "#d97706"],
  atr: ["#7a8290"],
};

// =============================================================================
// Component
// =============================================================================

export function CandleChart({
  bars,
  overlays = [],
  signals = [],
  executions = [],
  slTpLevels = [],
  drawings = [],
  activeTool = "select",
  onDrawingComplete,
  height,
  onCrosshairMove,
  onContextMenu,
}: CandleChartProps) {
  const drawingStartRef = useRef<DrawingCoord | null>(null);

  // Build candlestick trace
  const candleTrace: Plotly.Data = useMemo(() => {
    const x = bars.map((b) => b.ts);
    const open = bars.map((b) => b.o);
    const high = bars.map((b) => b.h);
    const low = bars.map((b) => b.l);
    const close = bars.map((b) => b.c);

    return {
      type: "candlestick" as const,
      x,
      open,
      high,
      low,
      close,
      increasing: {
        line: { color: THEME.candleUp },
        fillcolor: THEME.candleUp,
      },
      decreasing: {
        line: { color: THEME.candleDown },
        fillcolor: THEME.candleDown,
      },
      name: "OHLC",
      showlegend: false,
      hoverinfo: "x+text" as const,
      text: bars.map(
        (b) =>
          `O: ${b.o.toFixed(5)}<br>H: ${b.h.toFixed(5)}<br>L: ${b.l.toFixed(5)}<br>C: ${b.c.toFixed(5)}`
      ),
    };
  }, [bars]);

  // Build overlay traces
  const overlayTraces: Plotly.Data[] = useMemo(() => {
    const traces: Plotly.Data[] = [];

    overlays.forEach((overlay) => {
      const type = overlay.type.toLowerCase();
      const colors = OVERLAY_COLORS[type] ?? ["#5f6775"];

      Object.entries(overlay.values).forEach(
        ([valueName, values], valueIndex) => {
          const filtered = values.filter((v) => v.value !== null);
          if (filtered.length === 0) return;

          const isBollingerBand =
            type === "bollinger" && (valueName === "upper" || valueName === "lower");

          traces.push({
            type: "scatter" as const,
            mode: "lines" as const,
            x: filtered.map((v) => v.ts),
            y: filtered.map((v) => v.value as number),
            name: `${overlay.type} ${valueName}`,
            line: {
              color: colors[valueIndex % colors.length],
              width: 1,
              dash: isBollingerBand ? "dot" : "solid",
            },
            showlegend: false,
            hoverinfo: "skip" as const,
            ...(type === "bollinger" &&
              valueName === "lower" && {
                fill: "tonexty" as const,
                fillcolor: "rgba(122, 130, 144, 0.08)",
              }),
          });
        }
      );
    });

    return traces;
  }, [overlays]);

  // Build signal marker traces (per-strategy colors)
  const signalTrace: Plotly.Data | null = useMemo(() => {
    if (signals.length === 0) return null;

    return {
      type: "scatter" as const,
      mode: "markers" as const,
      x: signals.map((s) => s.ts),
      y: signals.map((s) => {
        // Find closest bar to position marker at low (BUY) or high (SELL)
        const bar = bars.find((b) => b.ts === s.ts);
        if (bar) return s.direction === "BUY" ? bar.l * 0.9998 : bar.h * 1.0002;
        return s.price ?? 0;
      }),
      marker: {
        symbol: signals.map((s) =>
          s.direction === "BUY" ? "triangle-up" : "triangle-down"
        ),
        color: signals.map((s) => getStrategyColor(s.strategy)),
        size: 10,
      },
      text: signals.map((s) => {
        const parts = [`${s.direction} ${s.strategy ?? s.source ?? ""}`];
        if (s.reason_codes && s.reason_codes.length > 0) {
          parts.push(s.reason_codes.join(", "));
        }
        if (s.stop_loss != null) parts.push(`SL: ${s.stop_loss.toFixed(5)}`);
        if (s.take_profit != null) parts.push(`TP: ${s.take_profit.toFixed(5)}`);
        return parts.join("<br>");
      }),
      hoverinfo: "text" as const,
      showlegend: false,
      name: "Signals",
    };
  }, [signals, bars]);

  // Build execution marker traces
  const execTrace: Plotly.Data | null = useMemo(() => {
    if (executions.length === 0) return null;

    return {
      type: "scatter" as const,
      mode: "markers" as const,
      x: executions.map((e) => e.ts),
      y: executions.map((e) => e.price),
      marker: {
        symbol: executions.map((e) =>
          e.type === "ENTRY" ? "diamond" : "star"
        ),
        color: executions.map((e) =>
          e.type === "ENTRY" ? THEME.entryBlue : THEME.exitYellow
        ),
        size: 11,
        line: { color: "#ffffff", width: 1 },
      },
      text: executions.map(
        (e) =>
          `${e.type}${e.bot ? ` (${e.bot})` : ""}${e.size ? ` ${e.size}` : ""}`
      ),
      hoverinfo: "text" as const,
      showlegend: false,
      name: "Executions",
    };
  }, [executions]);

  // Combine all traces
  const data: Plotly.Data[] = useMemo(() => {
    const traces: Plotly.Data[] = [candleTrace, ...overlayTraces];
    if (signalTrace) traces.push(signalTrace);
    if (execTrace) traces.push(execTrace);
    return traces;
  }, [candleTrace, overlayTraces, signalTrace, execTrace]);

  // Build SL/TP + signal SL/TP + drawing shapes
  const shapes: Partial<Plotly.Shape>[] = useMemo(() => {
    const s: Partial<Plotly.Shape>[] = [];

    // Signal SL/TP from latest signal per strategy (dotted lines)
    const latestByStrategy = new Map<string, Signal>();
    for (const sig of signals) {
      if (sig.strategy) latestByStrategy.set(sig.strategy, sig);
    }
    for (const [strategy, sig] of latestByStrategy) {
      const color = getStrategyColor(strategy);
      if (sig.stop_loss != null) {
        s.push({
          type: "line",
          xref: "paper",
          x0: 0,
          x1: 1,
          y0: sig.stop_loss,
          y1: sig.stop_loss,
          line: { color: THEME.slRed, width: 1, dash: "dot" },
        });
      }
      if (sig.take_profit != null) {
        s.push({
          type: "line",
          xref: "paper",
          x0: 0,
          x1: 1,
          y0: sig.take_profit,
          y1: sig.take_profit,
          line: { color: color, width: 1, dash: "dot" },
        });
      }
    }

    // SL/TP lines from live positions
    slTpLevels.forEach((level) => {
      s.push({
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        y0: level.price,
        y1: level.price,
        line: {
          color: level.type === "SL" ? THEME.slRed : THEME.tpGreen,
          width: 1,
          dash: "dash",
        },
      });
    });

    // User drawings
    drawings.forEach((drawing) => {
      switch (drawing.type) {
        case "horizontal":
          if (drawing.price == null) break;
          s.push({
            type: "line",
            xref: "paper",
            x0: 0,
            x1: 1,
            y0: drawing.price,
            y1: drawing.price,
            line: {
              color: drawing.color || "#2563eb",
              width: 1,
              dash: "solid",
            },
          });
          break;

        case "trendline":
          if (!drawing.p1 || !drawing.p2) break;
          s.push({
            type: "line",
            x0: new Date(drawing.p1.time * 1000).toISOString(),
            x1: new Date(drawing.p2.time * 1000).toISOString(),
            y0: drawing.p1.price,
            y1: drawing.p2.price,
            line: {
              color: drawing.color || "#2563eb",
              width: 1,
            },
          });
          break;

        case "ray":
          if (!drawing.p1 || !drawing.p2) break;
          {
            // Extend to right edge
            const lastBar = bars[bars.length - 1];
            const endTime = lastBar
              ? new Date(lastBar.ts).getTime() / 1000
              : drawing.p2.time;
            const dx = drawing.p2.time - drawing.p1.time;
            const dy = drawing.p2.price - drawing.p1.price;
            const factor =
              dx !== 0 ? (endTime - drawing.p1.time) / dx : 10;
            const endPrice = drawing.p1.price + dy * factor;

            s.push({
              type: "line",
              x0: new Date(drawing.p1.time * 1000).toISOString(),
              x1: new Date(endTime * 1000).toISOString(),
              y0: drawing.p1.price,
              y1: endPrice,
              line: {
                color: drawing.color || "#2563eb",
                width: 1,
              },
            });
          }
          break;

        case "rectangle":
          if (!drawing.topLeft || !drawing.bottomRight) break;
          s.push({
            type: "rect",
            x0: new Date(drawing.topLeft.time * 1000).toISOString(),
            x1: new Date(drawing.bottomRight.time * 1000).toISOString(),
            y0: drawing.topLeft.price,
            y1: drawing.bottomRight.price,
            line: {
              color: drawing.color || "#2563eb",
              width: 1,
              dash: "dash",
            },
            fillcolor: `${drawing.color || "#2563eb"}10`,
          });
          break;
      }
    });

    return s;
  }, [slTpLevels, drawings, bars, signals]);

  // Layout with shapes — use autosize to fill container; only set explicit
  // height when the caller provides one (e.g. dashboard mini-chart).
  const layout: Partial<Plotly.Layout> = useMemo(
    () => ({
      autosize: true,
      ...(height != null ? { height } : {}),
      xaxis: {
        type: "date" as const,
        rangeslider: { visible: false },
        gridcolor: "#e8ebf0",
        linecolor: "#d5d9e0",
      },
      yaxis: {
        side: "right" as const,
        gridcolor: "#e8ebf0",
        linecolor: "#d5d9e0",
      },
      shapes,
      margin: { l: 10, r: 60, t: 10, b: 30 },
      hovermode: "x unified" as const,
      dragmode: activeTool === "select" ? ("pan" as const) : (false as const),
    }),
    [height, shapes, activeTool]
  );

  const config: Partial<Plotly.Config> = useMemo(
    () => ({
      scrollZoom: true,
      displayModeBar: false as const,
    }),
    []
  );

  // Handle chart clicks for drawing tools
  const handleClick = useCallback(
    (event: Plotly.PlotMouseEvent) => {
      if (activeTool === "select" || !onDrawingComplete) return;
      if (!event.points || event.points.length === 0) return;

      const point = event.points[0];
      const time = new Date(point.x as string).getTime() / 1000;
      const price = point.y as number;
      const coord: DrawingCoord = { time, price };

      if (activeTool === "horizontal") {
        onDrawingComplete({
          type: "horizontal",
          symbol: "",
          timeframe: "",
          color: "",
          locked: false,
          price: coord.price,
        });
        return;
      }

      // Two-click tools
      if (!drawingStartRef.current) {
        drawingStartRef.current = coord;
        return;
      }

      const start = drawingStartRef.current;
      drawingStartRef.current = null;

      if (activeTool === "trendline" || activeTool === "ray") {
        onDrawingComplete({
          type: activeTool,
          symbol: "",
          timeframe: "",
          color: "",
          locked: false,
          p1: start,
          p2: coord,
        });
      } else if (activeTool === "rectangle") {
        onDrawingComplete({
          type: "rectangle",
          symbol: "",
          timeframe: "",
          color: "",
          locked: false,
          topLeft: {
            time: Math.min(start.time, coord.time),
            price: Math.max(start.price, coord.price),
          },
          bottomRight: {
            time: Math.max(start.time, coord.time),
            price: Math.min(start.price, coord.price),
          },
        });
      }
    },
    [activeTool, onDrawingComplete]
  );

  // Handle hover for crosshair callback
  const handleHover = useCallback(
    (event: Plotly.PlotHoverEvent) => {
      if (!onCrosshairMove || !event.points || event.points.length === 0)
        return;
      const point = event.points[0];
      const time = new Date(point.x as string).getTime() / 1000;
      const price = point.y as number;
      onCrosshairMove(time, price);
    },
    [onCrosshairMove]
  );

  // Count markers for legend
  const markerCounts = useMemo(() => {
    const buySignals = signals.filter((s) => s.direction === "BUY").length;
    const sellSignals = signals.filter((s) => s.direction === "SELL").length;
    const entries = executions.filter((e) => e.type === "ENTRY").length;
    const exits = executions.filter((e) => e.type === "EXIT").length;

    // Per-strategy counts
    const byStrategy = new Map<string, number>();
    for (const s of signals) {
      const key = s.strategy ?? "unknown";
      byStrategy.set(key, (byStrategy.get(key) ?? 0) + 1);
    }

    return { buySignals, sellSignals, entries, exits, byStrategy };
  }, [signals, executions]);

  const hasMarkers = signals.length > 0 || executions.length > 0;
  const hasSlTp = slTpLevels.length > 0;

  return (
    <div
      className="candle-chart-container"
      onContextMenu={onContextMenu}
      style={{ cursor: activeTool !== "select" ? "crosshair" : undefined }}
    >
      <div className="candle-chart">
        <PlotlyChart
          data={data}
          layout={layout}
          config={config}
          onClick={handleClick}
          onHover={handleHover}
        />
      </div>
      {(hasMarkers || hasSlTp) && (
        <div className="chart-legend">
          {/* Per-strategy signal counts */}
          {[...markerCounts.byStrategy.entries()].map(([strategy, count]) => (
            <span key={strategy} className="legend-item">
              <span
                className="legend-dot"
                style={{ background: getStrategyColor(strategy) }}
              />
              {strategy} ({count})
            </span>
          ))}
          {markerCounts.entries > 0 && (
            <span className="legend-item legend-entry">
              <span
                className="legend-dot"
                style={{ background: THEME.entryBlue }}
              />
              Entry ({markerCounts.entries})
            </span>
          )}
          {markerCounts.exits > 0 && (
            <span className="legend-item legend-exit">
              <span
                className="legend-dot"
                style={{ background: THEME.exitYellow }}
              />
              Exit ({markerCounts.exits})
            </span>
          )}
          {slTpLevels.filter((l) => l.type === "SL").length > 0 && (
            <span className="legend-item legend-sl">
              <span
                className="legend-line"
                style={{ borderColor: THEME.slRed }}
              />
              SL
            </span>
          )}
          {slTpLevels.filter((l) => l.type === "TP").length > 0 && (
            <span className="legend-item legend-tp">
              <span
                className="legend-line"
                style={{ borderColor: THEME.tpGreen }}
              />
              TP
            </span>
          )}
        </div>
      )}
    </div>
  );
}
