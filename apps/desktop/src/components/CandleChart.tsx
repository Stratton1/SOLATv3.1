/**
 * Candlestick chart component using lightweight-charts (TradingView).
 *
 * Features:
 * - OHLC candlesticks
 * - Line series overlays (EMA, SMA, etc.)
 * - Signal markers (BUY/SELL arrows)
 * - Execution markers (entry/exit)
 * - SL/TP horizontal price lines
 * - Auto-resize on container size change
 */

import {
  createChart,
  createSeriesMarkers,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  CandlestickSeries,
  LineSeries,
  LineData,
  SeriesMarker,
  Time,
  ColorType,
  CrosshairMode,
  ISeriesMarkersPluginApi,
} from "lightweight-charts";
import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { Bar, OverlayResult, Signal } from "../lib/engineClient";
import { Drawing, DrawingTool, DrawingCoord } from "../lib/drawings";
import {
  renderDrawing,
  removeRenderedDrawing,
  RenderedDrawing,
} from "../lib/chartDrawings";

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
  /** Fixed height in px. If undefined, chart fills container height. */
  height?: number;
  onCrosshairMove?: (time: Time | null, price: number | null) => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

// Overlay colors — readable on light background
const OVERLAY_COLORS: Record<string, string[]> = {
  ema: ["#2563eb", "#d97706", "#7c3aed", "#16a34a"],
  sma: ["#0891b2", "#db2777", "#ca8a04", "#059669"],
  bollinger: ["#6b7280", "#6b7280", "#6b7280"],
  ichimoku: ["#16a34a", "#dc2626", "#d97706", "#9da5b4", "#a78bfa"],
  rsi: ["#7c3aed"],
  macd: ["#2563eb", "#dc2626", "#16a34a"],
  stochastic: ["#2563eb", "#d97706"],
  atr: ["#6b7280"],
};

// Series API types
type CandleSeriesApi = ISeriesApi<"Candlestick">;
type LineSeriesApi = ISeriesApi<"Line">;

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
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<CandleSeriesApi | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const overlaySeriesRef = useRef<Map<string, LineSeriesApi>>(new Map());
  const slTpSeriesRef = useRef<Map<string, LineSeriesApi>>(new Map());
  const renderedDrawingsRef = useRef<RenderedDrawing[]>([]);

  // Drawing interaction state
  const drawingStartRef = useRef<DrawingCoord | null>(null);

  // Track container dimensions for dynamic sizing
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Observe container size changes
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height: h } = entry.contentRect;
        setDimensions({ width, height: h });
      }
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Effective height: fixed or container height
  const effectiveHeight = height ?? dimensions.height ?? 400;

  // Convert bars to chart data
  const candleData: CandlestickData<Time>[] = useMemo(
    () =>
      bars.map((bar) => ({
        time: (new Date(bar.ts).getTime() / 1000) as Time,
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
      })),
    [bars]
  );

  // Convert signals to markers
  const signalMarkers: SeriesMarker<Time>[] = useMemo(
    () =>
      signals.map((signal) => ({
        time: (new Date(signal.ts).getTime() / 1000) as Time,
        position:
          signal.direction === "BUY"
            ? ("belowBar" as const)
            : ("aboveBar" as const),
        color: signal.direction === "BUY" ? "#16a34a" : "#dc2626",
        shape:
          signal.direction === "BUY"
            ? ("arrowUp" as const)
            : ("arrowDown" as const),
        text: signal.source ?? signal.direction,
      })),
    [signals]
  );

  // Convert executions to markers
  const executionMarkers: SeriesMarker<Time>[] = useMemo(
    () =>
      executions.map((exec) => ({
        time: (new Date(exec.ts).getTime() / 1000) as Time,
        position:
          exec.direction === "BUY"
            ? ("belowBar" as const)
            : ("aboveBar" as const),
        color: exec.type === "ENTRY" ? "#2563eb" : "#d97706",
        shape:
          exec.direction === "BUY"
            ? ("arrowUp" as const)
            : ("arrowDown" as const),
        text: `${exec.type}${exec.bot ? ` (${exec.bot})` : ""}${exec.size ? ` ${exec.size}` : ""}`,
      })),
    [executions]
  );

  // Combine and sort markers
  const allMarkers = useMemo(
    () =>
      [...signalMarkers, ...executionMarkers].sort(
        (a, b) => (a.time as number) - (b.time as number)
      ),
    [signalMarkers, executionMarkers]
  );

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: effectiveHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#5c6370",
      },
      grid: {
        vertLines: { color: "#f0f1f3" },
        horzLines: { color: "#f0f1f3" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#9da5b4",
          width: 1,
          style: 3,
          labelBackgroundColor: "#eef0f4",
        },
        horzLine: {
          color: "#9da5b4",
          width: 1,
          style: 3,
          labelBackgroundColor: "#eef0f4",
        },
      },
      rightPriceScale: {
        borderColor: "#dfe1e6",
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      timeScale: {
        borderColor: "#dfe1e6",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Add candlestick series (v5 API)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    });
    candleSeriesRef.current = candleSeries;

    // Handle crosshair move
    if (onCrosshairMove) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.point) {
          onCrosshairMove(null, null);
          return;
        }
        const price = candleSeries.coordinateToPrice(param.point.y);
        onCrosshairMove(param.time, price);
      });
    }

    // Handle resize
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: height ?? containerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    // Capture ref values for cleanup
    const currentOverlaySeries = overlaySeriesRef.current;
    const currentSlTpSeries = slTpSeriesRef.current;

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      markersRef.current = null;
      currentOverlaySeries.clear();
      currentSlTpSeries.clear();
    };
  }, [height, effectiveHeight, onCrosshairMove]);

  // Update candle data
  useEffect(() => {
    if (!candleSeriesRef.current || candleData.length === 0) return;
    candleSeriesRef.current.setData(candleData);
  }, [candleData]);

  // Update markers (v5 API - use createSeriesMarkers)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // If markers primitive exists, update it; otherwise create it
    if (markersRef.current) {
      markersRef.current.setMarkers(allMarkers);
    } else if (allMarkers.length > 0) {
      markersRef.current = createSeriesMarkers(
        candleSeriesRef.current,
        allMarkers
      );
    }
  }, [allMarkers]);

  // Update overlays
  useEffect(() => {
    if (!chartRef.current) return;

    const chart = chartRef.current;
    const existingSeries = overlaySeriesRef.current;

    // Track which series keys we need
    const neededKeys = new Set<string>();

    overlays.forEach((overlay) => {
      const type = overlay.type.toLowerCase();
      const colors = OVERLAY_COLORS[type] ?? ["#888888"];

      Object.entries(overlay.values).forEach(
        ([valueName, values], valueIndex) => {
          const key = `${type}_${valueName}`;
          neededKeys.add(key);

          // Convert to line data
          const lineData: LineData<Time>[] = values
            .filter((v) => v.value !== null)
            .map((v) => ({
              time: (new Date(v.ts).getTime() / 1000) as Time,
              value: v.value as number,
            }));

          if (lineData.length === 0) return;

          // Get or create series (v5 API)
          let series = existingSeries.get(key);
          if (!series) {
            series = chart.addSeries(LineSeries, {
              color: colors[valueIndex % colors.length],
              lineWidth: 1,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            });
            existingSeries.set(key, series);
          }

          series.setData(lineData);
        }
      );
    });

    // Remove unused series
    existingSeries.forEach((series, key) => {
      if (!neededKeys.has(key)) {
        chart.removeSeries(series);
        existingSeries.delete(key);
      }
    });
  }, [overlays]);

  // Update SL/TP price lines
  useEffect(() => {
    if (!chartRef.current || candleData.length === 0) return;

    const chart = chartRef.current;
    const existingSeries = slTpSeriesRef.current;
    const neededKeys = new Set<string>();

    // Get time range from candle data for drawing horizontal lines
    const firstTime = candleData[0].time;
    const lastTime = candleData[candleData.length - 1].time;

    slTpLevels.forEach((level, idx) => {
      const key = `${level.type}_${idx}_${level.price}`;
      neededKeys.add(key);

      const isSL = level.type === "SL";
      const color = isSL ? "#dc2626" : "#16a34a";

      // Create two-point horizontal line spanning chart
      const lineData: LineData<Time>[] = [
        { time: firstTime, value: level.price },
        { time: lastTime, value: level.price },
      ];

      let series = existingSeries.get(key);
      if (!series) {
        series = chart.addSeries(LineSeries, {
          color,
          lineWidth: 1,
          lineStyle: 2, // dashed
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: false,
          title: `${level.type} ${level.price.toFixed(5)}`,
        });
        existingSeries.set(key, series);
      }

      series.setData(lineData);
    });

    // Remove stale SL/TP series
    existingSeries.forEach((series, key) => {
      if (!neededKeys.has(key)) {
        chart.removeSeries(series);
        existingSeries.delete(key);
      }
    });
  }, [slTpLevels, candleData]);

  // Render drawings
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || candleData.length === 0) return;

    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;

    // Remove old rendered drawings
    for (const rd of renderedDrawingsRef.current) {
      removeRenderedDrawing(chart, candleSeries, rd);
    }
    renderedDrawingsRef.current = [];

    // Render new drawings
    const firstTime = candleData[0].time as number;
    const lastTime = candleData[candleData.length - 1].time as number;

    for (const drawing of drawings) {
      const rd = renderDrawing(chart, candleSeries, drawing, {
        first: firstTime,
        last: lastTime,
      });
      renderedDrawingsRef.current.push(rd);
    }
  }, [drawings, candleData]);

  // Drawing click handler — captures chart coordinates for drawing tools
  useEffect(() => {
    if (!containerRef.current || !chartRef.current || !candleSeriesRef.current) return;
    if (activeTool === "select" || !onDrawingComplete) return;

    const container = containerRef.current;
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;

    const cb = onDrawingComplete;

    function handleClick(e: MouseEvent) {
      if (!cb) return;
      // Get chart coordinate from click position
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const time = chart.timeScale().coordinateToTime(x);
      const price = candleSeries.coordinateToPrice(y);
      if (time == null || price == null) return;

      const coord: DrawingCoord = { time: time as number, price };

      if (activeTool === "horizontal") {
        // Single click completes
        cb({
          type: "horizontal",
          symbol: "",  // Will be filled by parent
          timeframe: "",
          color: "",
          locked: false,
          price: coord.price,
        });
        return;
      }

      // Two-click tools: trendline, ray, rectangle
      if (!drawingStartRef.current) {
        drawingStartRef.current = coord;
        return;
      }

      const start = drawingStartRef.current;
      drawingStartRef.current = null;

      if (activeTool === "trendline" || activeTool === "ray") {
        cb({
          type: activeTool,
          symbol: "",
          timeframe: "",
          color: "",
          locked: false,
          p1: start,
          p2: coord,
        });
      } else if (activeTool === "rectangle") {
        cb({
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
    }

    container.addEventListener("click", handleClick);
    return () => container.removeEventListener("click", handleClick);
  }, [activeTool, onDrawingComplete]);

  // Fit content when data changes
  const fitContent = useCallback(() => {
    if (chartRef.current && candleData.length > 0) {
      chartRef.current.timeScale().fitContent();
    }
  }, [candleData.length]);

  useEffect(() => {
    fitContent();
  }, [fitContent]);

  // Count markers for legend
  const markerCounts = useMemo(() => {
    const buySignals = signalMarkers.filter(
      (m) => m.shape === "arrowUp"
    ).length;
    const sellSignals = signalMarkers.filter(
      (m) => m.shape === "arrowDown"
    ).length;
    const entries = executions.filter((e) => e.type === "ENTRY").length;
    const exits = executions.filter((e) => e.type === "EXIT").length;
    return { buySignals, sellSignals, entries, exits };
  }, [signalMarkers, executions]);

  const hasMarkers = allMarkers.length > 0;
  const hasSlTp = slTpLevels.length > 0;

  return (
    <div
      className="candle-chart-container"
      onContextMenu={onContextMenu}
      style={{ cursor: activeTool !== "select" ? "crosshair" : undefined }}
    >
      <div ref={containerRef} className="candle-chart" />
      {(hasMarkers || hasSlTp) && (
        <div className="chart-legend">
          {markerCounts.buySignals > 0 && (
            <span className="legend-item legend-buy-signal">
              <span className="legend-dot" style={{ background: "#16a34a" }} />
              Buy ({markerCounts.buySignals})
            </span>
          )}
          {markerCounts.sellSignals > 0 && (
            <span className="legend-item legend-sell-signal">
              <span className="legend-dot" style={{ background: "#dc2626" }} />
              Sell ({markerCounts.sellSignals})
            </span>
          )}
          {markerCounts.entries > 0 && (
            <span className="legend-item legend-entry">
              <span className="legend-dot" style={{ background: "#2563eb" }} />
              Entry ({markerCounts.entries})
            </span>
          )}
          {markerCounts.exits > 0 && (
            <span className="legend-item legend-exit">
              <span className="legend-dot" style={{ background: "#d97706" }} />
              Exit ({markerCounts.exits})
            </span>
          )}
          {slTpLevels.filter((l) => l.type === "SL").length > 0 && (
            <span className="legend-item legend-sl">
              <span
                className="legend-line"
                style={{ borderColor: "#dc2626" }}
              />
              SL
            </span>
          )}
          {slTpLevels.filter((l) => l.type === "TP").length > 0 && (
            <span className="legend-item legend-tp">
              <span
                className="legend-line"
                style={{ borderColor: "#16a34a" }}
              />
              TP
            </span>
          )}
        </div>
      )}
    </div>
  );
}
