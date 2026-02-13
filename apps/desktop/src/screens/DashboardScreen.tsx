/**
 * Dashboard — Bloomberg-style dense grid with KPIs, mini chart,
 * active strategies, positions, watchlist, equity curve, and signals.
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Plotly from "plotly.js-finance-dist";
import { PlotlyChart } from "../components/PlotlyChart";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useEngineHealth } from "../hooks/useEngineHealth";
import {
  engineClient,
  ExecutionFill,
  Bar,
  OpenPosition,
  Quote,
  AutopilotCombo,
  TerminalSignal,
} from "../lib/engineClient";
import { formatCurrency, formatPnl } from "../lib/format";

// =============================================================================
// Component
// =============================================================================

export function DashboardScreen() {
  const navigate = useNavigate();
  const { status } = useExecutionStatus();
  const { health, connectionState } = useEngineHealth();

  // Data state
  const [fills, setFills] = useState<ExecutionFill[]>([]);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [combos, setCombos] = useState<AutopilotCombo[]>([]);
  const [signals, setSignals] = useState<TerminalSignal[]>([]);
  const [miniBars, setMiniBars] = useState<Bar[]>([]);
  const [miniSymbol, setMiniSymbol] = useState<string>("");

  // Fetch fills for equity curve
  const fetchFills = useCallback(async () => {
    try {
      const res = await engineClient.getExecutionFills({ limit: 500 });
      setFills(res.fills);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch positions
  const fetchPositions = useCallback(async () => {
    try {
      const res = await engineClient.getPositions();
      setPositions(res.positions);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch quotes
  const fetchQuotes = useCallback(async () => {
    try {
      const res = await engineClient.getQuotes();
      setQuotes(res.quotes);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch autopilot combos
  const fetchCombos = useCallback(async () => {
    try {
      const res = await engineClient.getAutopilotCombos();
      setCombos(res.combos);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch recent signals
  const fetchSignals = useCallback(async () => {
    try {
      const res = await engineClient.getTerminalSignals({ limit: 20 });
      setSignals(res.signals);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch mini chart bars
  const fetchMiniBars = useCallback(async () => {
    try {
      // Try to get a symbol from allowlist first
      let sym = miniSymbol;
      if (!sym) {
        try {
          const al = await engineClient.getAllowlist();
          if (al.symbols.length > 0) sym = al.symbols[0];
        } catch {
          /* fallback */
        }
      }
      if (!sym) sym = "EUR/USD";
      setMiniSymbol(sym);

      const res = await engineClient.getBars(sym, "1h", { limit: 100 });
      setMiniBars(res.bars);
    } catch {
      /* engine may be offline */
    }
  }, [miniSymbol]);

  // Set up polling
  useEffect(() => {
    fetchFills();
    fetchPositions();
    fetchQuotes();
    fetchCombos();
    fetchSignals();
    fetchMiniBars();

    const intervals = [
      setInterval(fetchFills, 30000),
      setInterval(fetchPositions, 5000),
      setInterval(fetchQuotes, 3000),
      setInterval(fetchCombos, 10000),
      setInterval(fetchSignals, 5000),
      setInterval(fetchMiniBars, 60000),
    ];

    return () => intervals.forEach(clearInterval);
  }, [fetchFills, fetchPositions, fetchQuotes, fetchCombos, fetchSignals, fetchMiniBars]);

  // Derived values
  const engineUp = connectionState === "connected";
  const balance = status?.account_balance;
  const pnlToday = status?.realized_pnl_today ?? 0;

  const openCount = status?.open_position_count ?? 0;
  const mode = status?.mode ?? "---";

  // Build equity data from fills
  const equityData = useMemo(() => {
    const startingBalance = status?.account_balance ?? 10000;
    let running = startingBalance;
    const sorted = [...fills].sort(
      (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()
    );
    const points: { time: string; value: number }[] = [];
    for (const fill of sorted) {
      if (fill.pnl != null) running += fill.pnl;
      points.push({ time: fill.ts.slice(0, 10), value: running });
    }
    // Deduplicate by date
    const byDate = new Map<string, number>();
    for (const p of points) byDate.set(p.time, p.value);
    return Array.from(byDate.entries()).map(([time, value]) => ({ time, value }));
  }, [fills, status?.account_balance]);

  // Mini chart trace
  const miniChartData: Plotly.Data[] = useMemo(() => {
    if (miniBars.length === 0) return [];
    return [
      {
        type: "candlestick" as const,
        x: miniBars.map((b) => b.ts),
        open: miniBars.map((b) => b.o),
        high: miniBars.map((b) => b.h),
        low: miniBars.map((b) => b.l),
        close: miniBars.map((b) => b.c),
        increasing: { line: { color: "#00d68f" }, fillcolor: "#00d68f" },
        decreasing: { line: { color: "#f45b69" }, fillcolor: "#f45b69" },
        showlegend: false,
        hoverinfo: "skip" as const,
      },
    ];
  }, [miniBars]);

  // Equity trace
  const equityTraceData: Plotly.Data[] = useMemo(() => {
    if (equityData.length === 0) return [];
    return [
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: equityData.map((p) => p.time),
        y: equityData.map((p) => p.value),
        fill: "tozeroy" as const,
        fillcolor: "rgba(61, 139, 253, 0.12)",
        line: { color: "#3d8bfd", width: 2 },
        showlegend: false,
        hoverinfo: "x+y" as const,
      },
    ];
  }, [equityData]);

  return (
    <div className="dashboard-bloomberg">
      {/* Row 0: KPI Strip */}
      <div className="dash-kpi-strip">
        <div className="dash-kpi">
          <span className="dash-kpi-label">BALANCE</span>
          <span className="dash-kpi-value">
            {balance != null ? formatCurrency(balance) : "---"}
          </span>
        </div>
        <div className={`dash-kpi ${pnlToday >= 0 ? "kpi-pos" : "kpi-neg"}`}>
          <span className="dash-kpi-label">DAILY P&L</span>
          <span className="dash-kpi-value">
            {formatPnl(pnlToday)}
          </span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">POSITIONS</span>
          <span className="dash-kpi-value">{openCount}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">BOTS</span>
          <span className="dash-kpi-value">{combos.length || "0"}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">MODE</span>
          <span className={`dash-kpi-value mode-badge mode-${mode.toLowerCase()}`}>{mode}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">ENGINE</span>
          <span className="dash-kpi-value">
            <span className={`dash-led ${engineUp ? "led-ok" : "led-err"}`} />
            {engineUp ? `v${health?.version ?? "?"}` : "Offline"}
          </span>
        </div>
      </div>

      {/* Row 1: Mini Chart + Active Strategies */}
      <div className="dash-widget dash-area-chart">
        <div className="dash-widget-header">
          <span>CHART {miniSymbol && `\u2014 ${miniSymbol} (1H)`}</span>
        </div>
        <div
          className="dash-widget-body"
          style={{ cursor: "pointer" }}
          onClick={() => navigate("/terminal")}
        >
          {miniBars.length > 0 ? (
            <PlotlyChart
              data={miniChartData}
              layout={{
                height: 200,
                margin: { l: 5, r: 45, t: 5, b: 20 },
                xaxis: {
                  type: "date" as const,
                  rangeslider: { visible: false },
                  showgrid: false,
                  gridcolor: "#e8ebf0",
                  linecolor: "#d5d9e0",
                },
                yaxis: {
                  side: "right" as const,
                  gridcolor: "#e8ebf0",
                  linecolor: "#d5d9e0",
                },
                dragmode: false as const,
              }}
              config={{ displayModeBar: false, scrollZoom: false }}
            />
          ) : (
            <div className="dash-widget-empty">No bar data</div>
          )}
        </div>
      </div>

      <div className="dash-widget dash-area-strategies">
        <div className="dash-widget-header">
          <span>ACTIVE STRATEGIES</span>
          <span className="dash-widget-count">{combos.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {combos.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Bot</th>
                  <th>Symbol</th>
                  <th>TF</th>
                  <th>Buffer</th>
                </tr>
              </thead>
              <tbody>
                {combos.map((c, i) => (
                  <tr
                    key={i}
                    className="dash-row-clickable"
                    onClick={() => navigate("/terminal")}
                  >
                    <td className="mono">{c.bot}</td>
                    <td>{c.symbol}</td>
                    <td>{c.timeframe}</td>
                    <td className="num">{c.buffer_size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">
              No active strategies
              <span className="dash-widget-hint">Enable Autopilot in System</span>
            </div>
          )}
        </div>
      </div>

      {/* Row 2: Positions + Watchlist */}
      <div className="dash-widget dash-area-positions">
        <div className="dash-widget-header">
          <span>OPEN POSITIONS</span>
          <span className="dash-widget-count">{positions.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {positions.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Dir</th>
                  <th>Size</th>
                  <th>Entry</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td className="mono">{p.symbol}</td>
                    <td>
                      <span className={`dir-badge dir-${p.direction.toLowerCase()}`}>
                        {p.direction}
                      </span>
                    </td>
                    <td className="num">{p.size}</td>
                    <td className="num">{p.entry_price != null ? p.entry_price.toFixed(5) : "---"}</td>
                    <td className={`num ${(p.pnl ?? 0) >= 0 ? "positive" : "negative"}`}>
                      {p.pnl != null ? p.pnl.toFixed(2) : "---"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">No open positions</div>
          )}
        </div>
      </div>

      <div className="dash-widget dash-area-watchlist">
        <div className="dash-widget-header">
          <span>WATCHLIST</span>
          <span className="dash-widget-count">{Object.keys(quotes).length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {Object.keys(quotes).length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Spread</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(quotes).map((q, i) => (
                  <tr key={i}>
                    <td className="mono">{q.symbol}</td>
                    <td className="num">{q.bid != null ? q.bid.toFixed(5) : "---"}</td>
                    <td className="num">{q.ask != null ? q.ask.toFixed(5) : "---"}</td>
                    <td className="num">
                      {q.bid != null && q.ask != null
                        ? ((q.ask - q.bid) * 10000).toFixed(1)
                        : "---"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">
              Connect broker for live quotes
            </div>
          )}
        </div>
      </div>

      {/* Row 3: Equity Curve + Recent Signals */}
      <div className="dash-widget dash-area-equity">
        <div className="dash-widget-header">
          <span>EQUITY CURVE</span>
          <span className="dash-widget-count">{fills.length} fills</span>
        </div>
        <div className="dash-widget-body">
          {equityData.length > 0 ? (
            <PlotlyChart
              data={equityTraceData}
              layout={{
                height: 160,
                margin: { l: 50, r: 10, t: 5, b: 25 },
                xaxis: { type: "date" as const, gridcolor: "#e8ebf0", linecolor: "#d5d9e0" },
                yaxis: { gridcolor: "#e8ebf0", linecolor: "#d5d9e0" },
              }}
              config={{ displayModeBar: false, scrollZoom: false }}
            />
          ) : (
            <div className="dash-widget-empty">No fill data yet</div>
          )}
        </div>
      </div>

      <div className="dash-widget dash-area-signals">
        <div className="dash-widget-header">
          <span>RECENT SIGNALS</span>
          <span className="dash-widget-count">{signals.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {signals.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Bot</th>
                  <th>Symbol</th>
                  <th>Side</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={i}>
                    <td className="num">
                      {s.ts ? new Date(s.ts).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "---"}
                    </td>
                    <td className="mono">{s.bot ?? "---"}</td>
                    <td>{s.symbol ?? "---"}</td>
                    <td>
                      {s.side ? (
                        <span className={`dir-badge dir-${s.side.toLowerCase()}`}>
                          {s.side}
                        </span>
                      ) : (
                        "---"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">No signals yet</div>
          )}
        </div>
      </div>
    </div>
  );
}
