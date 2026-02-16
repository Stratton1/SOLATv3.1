/**
 * Candlestick chart component using Plotly.js.
 *
 * Features:
 * - OHLC candlesticks
 * - Line overlays (EMA, SMA, Bollinger, Ichimoku, etc.)
 * - Signal markers (BUY/SELL arrows) with white outline
 * - Execution markers (entry/exit)
 * - SL/TP shaded risk/reward zones + outcome hit markers
 * - Drawing tools (horizontal, trendline, ray, rectangle)
 * - Stable pan/zoom (shapes content-hashed, dynamic uirevision)
 * - Quick zoom via xRange prop
 * - Auto-resize
 */

import { useMemo, useCallback, useRef } from "react";
import Plotly from "plotly.js-finance-dist";
import { PlotlyChart } from "./PlotlyChart";
import { Bar, OverlayResult, Signal } from "../lib/engineClient";
import { Drawing, DrawingTool, DrawingCoord } from "../lib/drawings";
import { snapToCandle } from "../lib/timestamps";

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
  timeframe?: string;
  symbol?: string;
  /** Explicit x-axis range from zoom buttons or user pan */
  xRange?: [string, string] | null;
  /** Show range slider below chart */
  showRangeSlider?: boolean;
  onCrosshairMove?: (time: number | null, price: number | null) => void;
  onRelayout?: (event: Plotly.PlotRelayoutEvent) => void;
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
  rrLabel: "#a0a0b0",
};

/** Pip size for R:R pip-distance labels. */
function getPipSize(symbol: string): number {
  const s = (symbol ?? "").toUpperCase();
  if (s.includes("JPY")) return 0.01;
  if (s.startsWith("XAU")) return 0.1;
  if (s.startsWith("XAG")) return 0.01;
  return 0.0001;
}

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
  timeframe = "1h",
  symbol = "",
  xRange = null,
  showRangeSlider = false,
  onCrosshairMove,
  onRelayout,
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
      if (!overlay.values) return;
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

  // Pre-compute candle timestamps for signal alignment
  const candleTimestamps = useMemo(() => bars.map((b) => b.ts), [bars]);
  const barMap = useMemo(() => {
    const m = new Map<string, Bar>();
    for (const b of bars) m.set(b.ts, b);
    return m;
  }, [bars]);

  // Build signal marker traces (per-strategy colors) with timestamp alignment
  // 2C: Larger markers, white outline, dynamic offset from candle H/L
  const signalTrace: Plotly.Data | null = useMemo(() => {
    if (signals.length === 0) return null;

    const alignedSignals = signals.map((s) => ({
      ...s,
      alignedTs: snapToCandle(s.ts, candleTimestamps, timeframe),
    }));

    return {
      type: "scatter" as const,
      mode: "markers" as const,
      x: alignedSignals.map((s) => s.alignedTs),
      y: alignedSignals.map((s) => {
        const bar = barMap.get(s.alignedTs);
        if (bar) {
          const range = bar.h - bar.l;
          const offset = Math.max(range * 0.15, 0.0003);
          return s.direction === "BUY" ? bar.l - offset : bar.h + offset;
        }
        return s.price ?? 0;
      }),
      marker: {
        symbol: signals.map((s) =>
          s.direction === "BUY" ? "triangle-up" : "triangle-down"
        ),
        color: signals.map((s) => getStrategyColor(s.strategy)),
        size: 12,
        line: { color: "#ffffff", width: 1.5 },
      },
      text: signals.map((s) => {
        const parts = [`${s.direction} ${s.strategy ?? s.source ?? ""}`];
        if (s.reason_codes && s.reason_codes.length > 0) {
          parts.push(s.reason_codes.join(", "));
        }
        if (s.price != null) parts.push(`Entry: ${s.price.toFixed(5)}`);
        if (s.stop_loss != null) parts.push(`SL: ${s.stop_loss.toFixed(5)}`);
        if (s.take_profit != null) parts.push(`TP: ${s.take_profit.toFixed(5)}`);
        return parts.join("<br>");
      }),
      hoverinfo: "text" as const,
      showlegend: false,
      name: "Signals",
    };
  }, [signals, bars, candleTimestamps, timeframe, barMap]);

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

  // 2D: SL/TP outcome hit markers — find where SL or TP was hit for latest signals
  const hitMarkerTrace: Plotly.Data | null = useMemo(() => {
    if (signals.length === 0 || bars.length === 0) return null;

    const latestByStrategy = new Map<string, Signal>();
    for (const sig of signals) {
      if (sig.strategy) latestByStrategy.set(sig.strategy, sig);
    }

    const hitX: string[] = [];
    const hitY: number[] = [];
    const hitText: string[] = [];
    const hitColors: string[] = [];

    for (const [, sig] of latestByStrategy) {
      if (sig.price == null || (sig.stop_loss == null && sig.take_profit == null)) continue;

      const sigTime = new Date(sig.ts).getTime();
      const isBuy = sig.direction === "BUY";

      let slHitBar: Bar | null = null;
      let tpHitBar: Bar | null = null;

      for (const bar of bars) {
        const barTime = new Date(bar.ts).getTime();
        if (barTime <= sigTime) continue;

        if (sig.stop_loss != null && !slHitBar) {
          if (isBuy && bar.l <= sig.stop_loss) slHitBar = bar;
          if (!isBuy && bar.h >= sig.stop_loss) slHitBar = bar;
        }
        if (sig.take_profit != null && !tpHitBar) {
          if (isBuy && bar.h >= sig.take_profit) tpHitBar = bar;
          if (!isBuy && bar.l <= sig.take_profit) tpHitBar = bar;
        }

        if (slHitBar && tpHitBar) break;
      }

      // Whichever hit first
      if (slHitBar && tpHitBar) {
        const slTime = new Date(slHitBar.ts).getTime();
        const tpTime = new Date(tpHitBar.ts).getTime();
        if (slTime <= tpTime) {
          tpHitBar = null; // SL hit first
        } else {
          slHitBar = null; // TP hit first
        }
      }

      if (slHitBar && sig.stop_loss != null) {
        hitX.push(slHitBar.ts);
        hitY.push(sig.stop_loss);
        hitText.push("SL HIT");
        hitColors.push(THEME.slRed);
      }
      if (tpHitBar && sig.take_profit != null) {
        hitX.push(tpHitBar.ts);
        hitY.push(sig.take_profit);
        hitText.push("TP HIT");
        hitColors.push(THEME.tpGreen);
      }
    }

    if (hitX.length === 0) return null;

    return {
      type: "scatter" as const,
      mode: "markers+text" as const,
      x: hitX,
      y: hitY,
      marker: {
        symbol: "x" as const,
        color: hitColors,
        size: 10,
        line: { color: "#ffffff", width: 1 },
      },
      text: hitText,
      textposition: "top center" as const,
      textfont: { size: 8, color: "#9da5b4" },
      hoverinfo: "text" as const,
      showlegend: false,
      name: "SL/TP Outcomes",
    };
  }, [signals, bars]);

  // Combine all traces
  const data: Plotly.Data[] = useMemo(() => {
    const traces: Plotly.Data[] = [candleTrace, ...overlayTraces];
    if (signalTrace) traces.push(signalTrace);
    if (execTrace) traces.push(execTrace);
    if (hitMarkerTrace) traces.push(hitMarkerTrace);
    return traces;
  }, [candleTrace, overlayTraces, signalTrace, execTrace, hitMarkerTrace]);

  // Build SL/TP + signal SL/TP + drawing shapes + shaded risk/reward zones
  const shapes: Partial<Plotly.Shape>[] = useMemo(() => {
    const s: Partial<Plotly.Shape>[] = [];

    // Signal SL/TP from latest signal per strategy
    const latestByStrategy = new Map<string, Signal>();
    for (const sig of signals) {
      if (sig.strategy) latestByStrategy.set(sig.strategy, sig);
    }
    for (const [strategy, sig] of latestByStrategy) {
      const color = getStrategyColor(strategy);

      // 2D: Entry price line
      if (sig.price != null) {
        s.push({
          type: "line",
          xref: "paper",
          x0: 0,
          x1: 1,
          y0: sig.price,
          y1: sig.price,
          line: { color, width: 1, dash: "solid" },
        });
      }

      // SL line + shaded risk zone
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

        // 2D: Shaded risk zone (entry to SL)
        if (sig.price != null) {
          s.push({
            type: "rect",
            xref: "paper",
            x0: 0,
            x1: 1,
            y0: sig.price,
            y1: sig.stop_loss,
            line: { width: 0 },
            fillcolor: "rgba(244, 91, 105, 0.08)",
          });
        }
      }

      // TP line + shaded reward zone
      if (sig.take_profit != null) {
        s.push({
          type: "line",
          xref: "paper",
          x0: 0,
          x1: 1,
          y0: sig.take_profit,
          y1: sig.take_profit,
          line: { color, width: 1, dash: "dot" },
        });

        // 2D: Shaded reward zone (entry to TP)
        if (sig.price != null) {
          s.push({
            type: "rect",
            xref: "paper",
            x0: 0,
            x1: 1,
            y0: sig.price,
            y1: sig.take_profit,
            line: { width: 0 },
            fillcolor: "rgba(0, 214, 143, 0.08)",
          });
        }
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

  // 2A: Content-stabilize shapes to prevent Plotly re-render on every tick
  const shapesKey = useMemo(() => JSON.stringify(shapes), [shapes]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableShapes = useMemo(() => shapes, [shapesKey]);

  // R:R annotations for signal SL/TP zones
  const annotations: Partial<Plotly.Annotations>[] = useMemo(() => {
    const ann: Partial<Plotly.Annotations>[] = [];
    const pip = getPipSize(symbol ?? "");
    const latestByStrategy = new Map<string, Signal>();
    for (const sig of signals) {
      if (sig.strategy) latestByStrategy.set(sig.strategy, sig);
    }
    for (const [, sig] of latestByStrategy) {
      if (sig.price == null) continue;
      const entry = sig.price;
      const hasSl = sig.stop_loss != null;
      const hasTp = sig.take_profit != null;

      if (hasSl) {
        const slDist = Math.abs(entry - sig.stop_loss!);
        const slPips = Math.round(slDist / pip);
        ann.push({
          xref: "paper",
          yref: "y",
          x: 0.98,
          y: sig.stop_loss!,
          text: `SL ${slPips}p`,
          showarrow: false,
          font: { size: 9, color: THEME.slRed },
          xanchor: "right",
          bgcolor: "rgba(30,30,46,0.7)",
        });
      }

      if (hasTp) {
        const tpDist = Math.abs(sig.take_profit! - entry);
        const tpPips = Math.round(tpDist / pip);
        ann.push({
          xref: "paper",
          yref: "y",
          x: 0.98,
          y: sig.take_profit!,
          text: `TP ${tpPips}p`,
          showarrow: false,
          font: { size: 9, color: THEME.tpGreen },
          xanchor: "right",
          bgcolor: "rgba(30,30,46,0.7)",
        });
      }

      if (hasSl && hasTp) {
        const risk = Math.abs(entry - sig.stop_loss!);
        const reward = Math.abs(sig.take_profit! - entry);
        const rr = risk > 0 ? (reward / risk).toFixed(1) : "—";
        ann.push({
          xref: "paper",
          yref: "y",
          x: 0.98,
          y: entry,
          text: `R:R ${rr}:1`,
          showarrow: false,
          font: { size: 9, color: THEME.rrLabel },
          xanchor: "right",
          bgcolor: "rgba(30,30,46,0.7)",
        });
      }
    }
    return ann;
  }, [signals, symbol]);

  const annotationsKey = useMemo(() => JSON.stringify(annotations), [annotations]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableAnnotations = useMemo(() => annotations, [annotationsKey]);

  // Layout with shapes — use autosize to fill container
  const layout: Partial<Plotly.Layout> = useMemo(
    () => ({
      autosize: true,
      ...(height != null ? { height } : {}),
      xaxis: {
        type: "date" as const,
        rangeslider: { visible: showRangeSlider },
        gridcolor: "#e8ebf0",
        linecolor: "#d5d9e0",
        ...(xRange
          ? { range: xRange, autorange: false }
          : { autorange: true }),
      },
      yaxis: {
        side: "right" as const,
        gridcolor: "#e8ebf0",
        linecolor: "#d5d9e0",
        autorange: true,
      },
      shapes: stableShapes,
      annotations: stableAnnotations,
      margin: { l: 10, r: 60, t: 10, b: 30 },
      hovermode: "x unified" as const,
      hoverlabel: {
        bgcolor: "#1e1e2e",
        font: { size: 10, color: "#e0e0e0" },
        bordercolor: "#3a3a4a",
      },
      dragmode: activeTool === "select" ? ("pan" as const) : (false as const),
    }),
    [height, stableShapes, stableAnnotations, activeTool, xRange, showRangeSlider]
  );

  const config: Partial<Plotly.Config> = useMemo(
    () => ({
      scrollZoom: true,
      displayModeBar: false as const,
    }),
    []
  );

  // 2A: Dynamic uirevision — resets on symbol/timeframe change, stable otherwise
  const uirevision = useMemo(
    () => `${symbol}:${timeframe}`,
    [symbol, timeframe]
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
          onRelayout={onRelayout}
          uirevision={uirevision}
        />
      </div>
      {(hasMarkers || hasSlTp) && (
        <div className="chart-legend">
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
