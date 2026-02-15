/**
 * Overlay Playground — interactive indicator exploration.
 *
 * Features:
 * - Select symbol + timeframe, toggle indicators on/off
 * - Live chart preview with selected overlays
 * - Indicator parameter reference
 */

import { useState, useEffect, useCallback } from "react";
import { SummaryBar } from "../components/ui/SummaryBar";
import { Panel } from "../components/ui/Panel";
import { EmptyState } from "../components/ui/EmptyState";
import { useEngineHealth } from "../hooks/useEngineHealth";
import { engineClient, Bar, OverlayResult } from "../lib/engineClient";
import { CandleChart } from "../components/CandleChart";

const AVAILABLE_INDICATORS = [
  { id: "ema_9", label: "EMA(9)", group: "Moving Averages" },
  { id: "ema_20", label: "EMA(20)", group: "Moving Averages" },
  { id: "ema_50", label: "EMA(50)", group: "Moving Averages" },
  { id: "sma_20", label: "SMA(20)", group: "Moving Averages" },
  { id: "sma_50", label: "SMA(50)", group: "Moving Averages" },
  { id: "sma_200", label: "SMA(200)", group: "Moving Averages" },
  { id: "rsi_14", label: "RSI(14)", group: "Oscillators" },
  { id: "macd", label: "MACD", group: "Oscillators" },
  { id: "bb_20_2", label: "Bollinger(20,2)", group: "Bands" },
  { id: "ichimoku", label: "Ichimoku Cloud", group: "Complex" },
] as const;

const SYMBOLS = [
  "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
  "EURGBP", "EURJPY", "GBPJPY", "USDCAD", "NZDUSD",
];

const TIMEFRAMES = ["1h", "4h"];

export function PlaygroundScreen() {
  const { health } = useEngineHealth();
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("1h");
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(
    new Set(["ema_20", "ema_50"])
  );
  const [bars, setBars] = useState<Bar[]>([]);
  const [overlays, setOverlays] = useState<OverlayResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleIndicator = useCallback((id: string) => {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const barsRes = await engineClient.getBars(symbol, timeframe, { limit: 300 });
      setBars(barsRes.bars);

      if (activeIndicators.size > 0) {
        const overlayRes = await engineClient.computeOverlays({
          symbol,
          timeframe,
          indicators: [...activeIndicators],
          limit: 300,
        });
        setOverlays(overlayRes.overlays);
      } else {
        setOverlays([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, activeIndicators]);

  useEffect(() => {
    if (health?.status === "healthy") {
      fetchData();
    }
  }, [fetchData, health?.status]);

  const groups = AVAILABLE_INDICATORS.reduce<Record<string, typeof AVAILABLE_INDICATORS[number][]>>(
    (acc, ind) => {
      if (!acc[ind.group]) acc[ind.group] = [];
      acc[ind.group].push(ind);
      return acc;
    },
    {}
  );

  return (
    <div className="screen-layout">
      <SummaryBar
        pageId="playground"
        title="Overlay Playground"
        description="Explore technical indicators on any symbol. Toggle overlays on/off to see them rendered on the chart in real-time."
        actions={[
          "Select a symbol and timeframe to load chart data",
          "Toggle indicators to see them on the chart",
          "Compare multiple indicators simultaneously",
        ]}
        chips={[
          { label: "Active", value: `${activeIndicators.size}`, variant: "info" },
          { label: "Bars", value: `${bars.length}`, variant: "default" },
          { label: "Engine", value: health?.status === "healthy" ? "Online" : "Offline",
            variant: health?.status === "healthy" ? "success" : "danger" },
        ]}
      />

      <div className="screen-content-grid playground-layout">
        {/* Left: Controls */}
        <div className="playground-controls">
          <Panel title="Symbol & Timeframe">
            <div style={{ display: "flex", gap: 8 }}>
              <select
                className="ui-select"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                style={{ flex: 1 }}
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <select
                className="ui-select"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                style={{ width: 70 }}
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
          </Panel>

          <Panel title="Indicators" scrollable>
            {Object.entries(groups).map(([group, indicators]) => (
              <div key={group} style={{ marginBottom: 12 }}>
                <div style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  marginBottom: 4,
                }}>
                  {group}
                </div>
                {indicators.map((ind) => (
                  <label
                    key={ind.id}
                    className={`layer-toggle ${activeIndicators.has(ind.id) ? "active" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={activeIndicators.has(ind.id)}
                      onChange={() => toggleIndicator(ind.id)}
                    />
                    <span>{ind.label}</span>
                  </label>
                ))}
              </div>
            ))}
          </Panel>
        </div>

        {/* Right: Chart */}
        <div className="playground-chart">
          {health?.status !== "healthy" ? (
            <EmptyState
              title="Engine Offline"
              description="Start the engine to load chart data and overlays."
            />
          ) : loading && bars.length === 0 ? (
            <EmptyState
              title="Loading chart data..."
              description={`Fetching ${symbol} ${timeframe} bars`}
            />
          ) : error ? (
            <EmptyState
              title="Failed to load data"
              description={error}
              actionLabel="Retry"
              onAction={fetchData}
            />
          ) : bars.length === 0 ? (
            <EmptyState
              title="No data available"
              description={`No bars found for ${symbol} ${timeframe}. Sync data first.`}
            />
          ) : (
            <CandleChart
              bars={bars}
              signals={[]}
              overlays={overlays}
              timeframe={timeframe}
            />
          )}
        </div>
      </div>
    </div>
  );
}
